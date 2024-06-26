import requests
import json
from scrapingbee import ScrapingBeeClient
import trafilatura
import instructor
from pydantic import BaseModel, Field, field_validator, AfterValidator
from typing_extensions import Literal,Annotated
from typing import List, Dict, Optional
import tiktoken
import regex as re
from openai import OpenAI


def handler(event, context):
    # print(event)
    eventBody = event['queryStringParameters']
    QUERY = eventBody['query']
    TOTAL = int(eventBody['num_result'])
    NUMBER_OF_RESULTS = str(int(TOTAL*2))
    THRESHOLD = 8


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
                
                'search': QUERY,
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
    Is there a specific, {QUERY} in the following text? It has to contain specific details about {QUERY}, and cannot reference videos or other sites. If so, return "Yes". If not, return "No".
        '''.format(QUERY=QUERY)

    prompt2 = '''
        Given that there is a specific, {QUERY} in the text, extract it.
        '''.format(QUERY=QUERY)

    # clientYesNo = instructor.from_gemini(client=genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest", 
    #     system_instruction=prompt1
    #     ),
    #     mode=instructor.Mode.GEMINI_JSON)
    clientOA = instructor.patch(OpenAI(api_key='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'))

    requirements = clientOA.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": 'what basic descriptions, characteristics, etc. should a {QUERY} have? Do not give an example. Must be short.'.format(QUERY=QUERY)}], max_tokens=4096
                )


    # print(requirements.model_dump()['choices'][0]['message']['content'])
    reqConvert = str(requirements.model_dump()['choices'][0]['message']['content'])
    reqConvert = reqConvert.replace('\n', ' ')
    # print(reqConvert)



    class isQuery(BaseModel):
        # contains_specifics: bool = Field(description="contains all of these specifics: {reqConvert}")
        score: int = Field(description='does the text contain the necessary information to be a good {QUERY}, 0-10'.format(QUERY=QUERY))
        exec(f'is_this_a_{QUERY.replace(" ", "_")}: bool = Field(description="is this a {QUERY}")')

    class item(BaseModel):
        exec(f'{QUERY.replace(" ", "_")}: str = Field(description="{QUERY}")')
        exec(f'''contains_specifics: bool = Field(description="is this a {QUERY} and contains all of these specifics: {reqConvert}")''')

    class query(BaseModel):
        properties: List[item]

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
            messages=[{'role':"system", "content":prompt1},{"role": "user", "content": cleantext}], response_model=isQuery, max_tokens=4096
            )
            # hasThing = resp.model_dump()['contains_specifics']
            score = resp.model_dump()['score']
            check = resp.model_dump()[f'is_this_a_{QUERY.replace(" ", "_")}']
            if score > THRESHOLD and check:
                # print(resp.model_dump()['score'])
                resp = clientOA.chat.completions.create(
                model="gpt-4o",
                messages=[{'role':"system", "content":prompt2},{"role": "user", "content": cleantext}], response_model=query, max_tokens=4096
                )
                return resp.model_dump()['properties']
            else:
                return None
        except Exception as e:
            print(f'Failed to process URL {url}: {str(e)}')
            return None
        
    urls = []
    # print(results)
    for i in range(len(results['organic_results'])):
        urls.append(results['organic_results'][i]['url'])
    results = []
    # print(len(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result!=None:
                    results.append(result)
                    if len(results) >= TOTAL:
                        response = {"statusCode": 200, "body": json.dumps(results)}
                        return response
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')

    response = {"statusCode": 200, "body": json.dumps(results)}
    return response

if __name__ == '__main__':
    handler('','')
    




    
