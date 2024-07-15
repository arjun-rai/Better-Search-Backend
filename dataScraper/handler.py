import requests
import json
from scrapingbee import ScrapingBeeClient
import trafilatura
import instructor
from pydantic import BaseModel, Field, field_validator, AfterValidator, FieldValidationInfo
from typing_extensions import Literal,Annotated
from typing import List, Dict, Optional
import tiktoken
import regex as re
from openai import OpenAI
import boto3
import datetime


def handler(event, context):
    eventBody = event['queryStringParameters']
    QUERY = re.sub('[^A-Za-z0-9]+ ', '', eventBody['query'])
    TOTAL = int(eventBody['num_result'])
    USER = eventBody['user']
    # QUERY='best gaming CPU'
    # TOTAL=10
    # USER='asrrai09876@gmail.com'
    NUMBER_OF_RESULTS = str(int(TOTAL))
    THRESHOLD = 5 

    items_ = json.loads(requests.get('https://t5frigw267.execute-api.us-east-1.amazonaws.com/default/dataScraper-dev-data-scraper?userID=' + 'asrrai09876@gmail.com').content)['Items']
    if len(items_)>0:
        num_done = int(items_[len(items_)-1]['Count']['N'])
    else:
        num_done =0

    if num_done>4:
        print('OUT OF SEARCHES')
        return None


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
    for i in range(2): #30
        instructions_list.append({"scroll_y": 1080})
        instructions_list.append({"wait": 350})


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
    
    def scrape_images(item):
       imgs_json = requests.get('https://www.googleapis.com/customsearch/v1?key=AIzaSyDXz89jRij33XB0UIvMwwmvRSpz3AyJfH0&cx=01bdba7c3ca044dec&searchType=image&q='+item.replace(' ', '+')).json()
       return imgs_json['items'][0]['link']


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

    # prompt2 = '''
    #     Given that there is a specific, {QUERY} in the text, extract it.
    #     '''.format(QUERY=QUERY)

    # clientYesNo = instructor.from_gemini(client=genai.GenerativeModel(model_name="models/gemini-1.5-pro-latest", 
    #     system_instruction=prompt1
    #     ),
    #     mode=instructor.Mode.GEMINI_JSON)
    clientOA = instructor.patch(OpenAI(api_key='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'))


    class prompt(BaseModel):
        prompt: str=Field(description="system prompt for assisstant")

    requirements = clientOA.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": 'write a system prompt to find the {QUERY} in a given provided webpage. Make sure there are no duplicates.'.format(QUERY=QUERY)}], max_tokens=4096, response_model=prompt
                )

    # print(requirements)
  
    # print(requirements.model_dump()['prompt'])
#     reqConvert = str(requirements.model_dump()['choices'][0]['message']['content'])
#     reqConvert = reqConvert.replace('\n', ' ')
#     # print(reqConvert)

    alreadyIn=[]
    # alreadyInNum=[1]*(100)
    class isQuery(BaseModel):
        # contains_specifics: bool = Field(description="contains all of these specifics: {reqConvert}")
        score: int = Field(description='does the text contain the necessary information for {QUERY}, 0-10'.format(QUERY=QUERY))
        # exec(f'is_this_a_{QUERY.replace(" ", "_")}: bool = Field(description="is this a {QUERY}")')

    class item(BaseModel):
        exec(f'{QUERY.replace(" ", "_")}: str = Field(description="{QUERY}")')
        # exec(f'''contains_specifics: bool = Field(description="is this a {QUERY} and contains all of these specifics: {reqConvert}")''')
        not_already_in_list: bool =Field(description=f'is the item in the list or very similar to one? True or False: "{",".join(alreadyIn)}"'.format(alreadyIn))
        desc: str = Field(description='Why is this good? What are the good factors about it and what is are the relevant details. (keep concise)')
        cost: Optional[str] = Field(description="price of item, must include currency")
        


        @field_validator('not_already_in_list', mode='before')
        def must_not_be_in_list(cls, v, info: FieldValidationInfo):
            # # Check the values of both field1 and field2
            field2 = v if info.field_name == QUERY.replace(" ", "_") else info.data.get(QUERY.replace(" ", "_"))

            alreadyIn.append(field2)
               
                # raise ValueError('has to be not already in the list')
            return v


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
            # check = resp.model_dump()[f'is_this_a_{QUERY.replace(" ", "_")}']
            if score > THRESHOLD:
                # print(resp.model_dump()['score'])
                resp = clientOA.chat.completions.create(
                model="gpt-4o",
                messages=[{'role':"system", "content":requirements.model_dump()['prompt']},{"role": "user", "content": cleantext}], response_model=query, max_tokens=4096
                )
                # for entry in resp.model_dump()['properties']:
                #     alreadyIn.append(entry[QUERY.replace(' ','_')])
                return resp.model_dump()['properties']
            else:
                return None
        except Exception as e:
            print(f'Failed to process URL {url}: {str(e)}')
            return None
        
    DBresource = boto3.resource("dynamodb", region_name='us-east-1')
    dymaboDB = DBresource.Table('dataSets')
    urls = []
    # print(results)
    for i in range(len(results['organic_results'])):
        urls.append(results['organic_results'][i]['url'])
    results = []
    imgs = []
    sources = {}
    # print(len(urls))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result!=None:
                    newResult =[]
                    for entry in result:
                        if entry[QUERY.replace(' ', '_')].lower() in sources and entry['not_already_in_list']:
                            sources[entry[QUERY.replace(' ', '_')].lower()].append(url)
                        else:
                            sources[entry[QUERY.replace(' ', '_')].lower()] = [url]
                            imgs.append(scrape_images(entry[QUERY.replace(' ','_')]))
                            newResult.append(entry)
                    results.extend(newResult)
                    # if len(results) >= TOTAL:
                    #     break
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')
    currentTime = datetime.datetime.utcnow().isoformat()
    # print(imgs[0][0])
    # print(sources)
    # print(type(currentTime))
    
    dymaboDB.put_item(Item={'userID': USER, 'title':QUERY, 'data':json.dumps(results), 'timestamp':currentTime,'image_urls':json.dumps(imgs), 'source_urls':json.dumps(sources), 'Count':num_done+1, 'visible':True})

    response = {"statusCode": 200, 'headers' : {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Credentials': True,}}
    return response


# if __name__ == '__main__':
#     handler('','')



