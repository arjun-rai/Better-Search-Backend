import requests
import json
from scrapingbee import ScrapingBeeClient
from urllib.parse import urlparse
import trafilatura
import instructor
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from pydantic import BaseModel, Field, field_validator, AfterValidator
from typing_extensions import Literal,Annotated
from typing import List, Dict, Optional
import tiktoken
import regex as re

TYPE_OF_WORKOUT_PLAN = 'yoga'
NUMBER_OF_RESULTS = '100'
TOTAL_WORKOUTS = 10


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def google():
    response = requests.get(
        url='https://app.scrapingbee.com/api/v1/store/google',
        params={
            'api_key': 'XGE6ILA4M49F1UN6CFD8DBKJ4M9J6E96RSEDRRTUXFM37QBSMHW3SOENTSNUVHRWKV4AQ0O9YFHD3STF',
             
            'search': TYPE_OF_WORKOUT_PLAN + ' workout plans',
            'language': 'en', 
            'nb_results':NUMBER_OF_RESULTS,
        },
        
    )
    return response.status_code, response.text

results = json.loads(google()[1])

SBclient = ScrapingBeeClient(api_key='XGE6ILA4M49F1UN6CFD8DBKJ4M9J6E96RSEDRRTUXFM37QBSMHW3SOENTSNUVHRWKV4AQ0O9YFHD3STF')

instructions_list = []
for i in range(5): #30
    instructions_list.append({"scroll_y": 1080})
    instructions_list.append({"wait": 700})


def scrape_page_urls(url):
    response = SBclient.get(
    url,
    params={ 
    "render_js": "false",
    "extract_rules":{
                    "all_links":{
                        "selector":"a@href",
                        "type":"list"
                    }
                    },
    },)  
    return response.status_code, response.content
def scrape_page_content(url):
    response = SBclient.get(
    url,
    params={ 
        "render_js": "true",
        'js_scenario': {"instructions": instructions_list
            }
    },
    )  
    return response.status_code, response.content


#BAN YOUTUBE?
urls = []
for i in range(len(results['organic_results'])):
    urls.append(results['organic_results'][i]['url'])


safety_settings = [
    {
        "category": "HARM_CATEGORY_DANGEROUS",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE",
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE",
    },
    ]

prompt = '''
   You are an expert fitness trainer looking for structured workout plans. Structured workout plans have multiple specific exercises, as well as the needed specified parameters to do the exercises, like number of reps, sets, time duration, or etc. 
    The workout plans must contain all of the necessary information for anyone to actually do the exercises. 
    For example legs for 3 sets of 5 reps does not make sense since legs is not an exercise.
    You are to check if the given text has complete structured workout plans in it, return "yes" if there is one, and "no" if there is not one. If the answer is "yes," also return the complete structured workout plans. Everything about the workout plan MUST be specified, otherwise there is no workout plan. 
    If the workout plan refers to something else on the page (like a chart) make sure to include it in the workout plan. Extract the workout plans from the message and return only the workout plans in a structured format.
    '''
genai.configure(api_key='AIzaSyCapu0rOU5yJa_W3tK9RJf2p7u8wmDiWNU')
clientG = instructor.from_gemini(client=genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest", 
    safety_settings=safety_settings,
    generation_config={
        "temperature":0.2,
        'top_k':1,
        'top_p':1,
    },
    system_instruction=prompt
    ),
    mode=instructor.Mode.GEMINI_JSON)

class isPlan(BaseModel):
    contains_complete_workout_plan: bool = Field(description='contains complete structured workout plan, does not reference video or other sites')
    workout_plan: str = Field(description='complete workout plan with >3 movements/exercises/etc per day')
    additional_information: str = Field(description='additional information for the workout plan')
    workout_title: str = Field(description='should be an informative name summarizing what the workout plan')
class plans(BaseModel):
    properties: List[isPlan]


import concurrent.futures

def process_url(url):
    print(f'Processing URL: {url}')
    page_content = scrape_page_content(url)
    cleantext = trafilatura.extract(page_content[1], include_comments=False)
    if not isinstance(cleantext, str):
        return None
    cleantext = re.sub(r'\s+', ' ', cleantext).strip()
    cleantext = re.sub(r'[\n\r\t]', ' ', cleantext)
    cleantext = re.sub(r'[^\w\s\/\-]', '', cleantext)
    # print(num_tokens_from_string(cleantext, 'cl100k_base'))
    try:
        resp = clientG.messages.create(
            messages=[{"role": "user", "content": cleantext}],
            response_model=plans,
            strict=False
        )
        results = resp.model_dump()['properties']
        if results is None:
            return None
        return [(workout, url) for workout in results if workout['contains_complete_workout_plan']]
    except Exception as e:
        print(f'Failed to process URL {url}: {str(e)}')
        return None

def main():
    workouts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    for workout, url in result:
                        workout['url'] = url
                        workouts.append(workout)
                        if len(workouts) >= TOTAL_WORKOUTS:
                            return workouts
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')
    return workouts

if __name__ == "__main__":
    workouts = main()
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(workouts, f, ensure_ascii=False, indent=4)
    


