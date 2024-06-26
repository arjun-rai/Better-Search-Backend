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
from openai import OpenAI

TYPE_OF_WORKOUT_PLAN = 'HIIT'
NUMBER_OF_RESULTS = '20'
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


# safety_settings = [
#     {
#         "category": "HARM_CATEGORY_DANGEROUS",
#         "threshold": "BLOCK_NONE",
#     },
#     {
#         "category": "HARM_CATEGORY_HARASSMENT",
#         "threshold": "BLOCK_NONE",
#     },
#     {
#         "category": "HARM_CATEGORY_HATE_SPEECH",
#         "threshold": "BLOCK_NONE",
#     },
#     {
#         "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
#         "threshold": "BLOCK_NONE",
#     },
#     {
#         "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
#         "threshold": "BLOCK_NONE",
#     },
#     ]

prompt1 = '''
   Is there a specific, structured workout plan in the following text? It has to contain specific exercises and sets/reps/times, and cannot reference videos. Each excercise has to have a name that is a string. If so, return "Yes" and the complete structured workout plan. If not, return "No".
    '''

prompt2 = '''
    Given that there is a specific, structured workout plan in the text, extract it.
    '''
genai.configure(api_key='AIzaSyCapu0rOU5yJa_W3tK9RJf2p7u8wmDiWNU')
# clientYesNo = instructor.from_gemini(client=genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest", 
#     system_instruction=prompt1
#     ),
#     mode=instructor.Mode.GEMINI_JSON)
clientOA = instructor.patch(OpenAI(api_key='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'))

class isPlan(BaseModel):
    contains_complete_workout_plan: bool = Field(description='contains complete structured workout plan, does not reference video or other sites')
    score: int = Field(description='does the plan contain the necessary information to be a good workout plan, 0-10')

class Plan(BaseModel):
    plan: str = Field(description='complete structured workout plan')

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
        # resp = clientYesNo.messages.create(
        #     messages=[{"role": "user", "content": cleantext}],
        #     response_model=isPlan,
        #     strict=True
        # )
        resp = clientOA.chat.completions.create(
        model="gpt-4o",
        messages=[{'role':"system", "content":prompt1},{"role": "user", "content": cleantext}], response_model=isPlan, max_tokens=4096
        )
        hasPlan = resp.model_dump()['contains_complete_workout_plan']
        score = resp.model_dump()['score']
        if hasPlan and score > 9:
            # print(resp.model_dump()['score'])
            resp = clientOA.chat.completions.create(
            model="gpt-4o",
            messages=[{'role':"system", "content":prompt2},{"role": "user", "content": cleantext}], response_model=Plan, max_tokens=4096
            )
            return resp.model_dump()['plan']
        else:
            return None
    except Exception as e:
        print(f'Failed to process URL {url}: {str(e)}')
        return None

def main():
    workouts = []
    # print(len(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result!=None:
                    workouts.append(result)
                    if len(workouts) >= TOTAL_WORKOUTS:
                        return workouts
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')
    return workouts

if __name__ == "__main__":
    workouts = main()
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(workouts, f, ensure_ascii=False, indent=4)
    


