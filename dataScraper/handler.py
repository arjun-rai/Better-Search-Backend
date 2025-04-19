import requests
import json
from scrapingbee import ScrapingBeeClient
import trafilatura
import instructor
from pydantic import BaseModel, Field, field_validator, AfterValidator, FieldValidationInfo
from typing_extensions import Literal,Annotated
from typing import List, Dict, Optional
# import tiktoken
import regex as re
from openai import OpenAI
import boto3
import datetime
import os
from difflib import SequenceMatcher
import time
import random
from openai import APIError, RateLimitError, APIConnectionError


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

    items_ = json.loads(requests.get('https://t5frigw267.execute-api.us-east-1.amazonaws.com/default/dataScraper-dev-data-scraper?userID=' + USER).content)['Items']
    if len(items_)>0:
        num_done = int(items_[len(items_)-1]['Count']['N'])
        # print(items_[len(items_)-1])
        # print(num_done)
    else:
        num_done =0

    if num_done>4:
        print('OUT OF SEARCHES')
        return None


    # def num_tokens_from_string(string: str, encoding_name: str) -> int:
    #     """Returns the number of tokens in a text string."""
    #     encoding = tiktoken.get_encoding(encoding_name)
    #     num_tokens = len(encoding.encode(string))
    #     return num_tokens

    def google():
        response = requests.get(
            url='https://app.scrapingbee.com/api/v1/store/google',
            params={
                'api_key': os.environ["SB_API_KEY"],
                
                'search': QUERY,
                'language': 'en', 
                'nb_results':NUMBER_OF_RESULTS,
            },
            
        )
        return response.status_code, response.text

    results = json.loads(google()[1])

    SBclient = ScrapingBeeClient(api_key=os.environ["SB_API_KEY"])

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
       imgs_json = requests.get('https://www.googleapis.com/customsearch/v1?key='+os.environ['google_API_KEY']+'&cx=01bdba7c3ca044dec&searchType=image&q='+item.replace(' ', '+')).json()
       return imgs_json['items'][0]['link']

    def is_similar_product(product1, product2, threshold=0.65):
        """
        Compare two product names using string similarity and determine if they are the same product.
        Returns True if they are considered similar enough, False otherwise.
        """
        # Clean the names - remove common prefixes/suffixes, spaces, lowercase
        p1 = re.sub(r'[^\w\s]', '', product1.lower()).strip()
        p2 = re.sub(r'[^\w\s]', '', product2.lower()).strip()
        
        # SequenceMatcher for string similarity
        similarity = SequenceMatcher(None, p1, p2).ratio()
        
        # Return True if similarity is above threshold
        return similarity >= threshold

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
    clientOA = instructor.patch(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))


    def make_openai_call(model, messages, response_model=None, max_tokens=4096, max_retries=5, initial_backoff=1):
        """
        Make an OpenAI API call with exponential backoff for rate limits
        """
        retries = 0
        backoff = initial_backoff
        
        while retries <= max_retries:
            try:
                # Add a small random sleep between API calls to avoid rate limits
                if retries > 0:
                    # Small jitter to avoid thundering herd problem
                    jitter = random.uniform(0, 0.5)
                    time.sleep(backoff + jitter)
                    print(f"Retry {retries} after {backoff}s backoff")
                
                # Make the API call
                if response_model:
                    result = clientOA.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_model=response_model,
                        max_tokens=max_tokens
                    )
                else:
                    result = clientOA.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens
                    )
                
                # Successful call, return result
                return result
                
            except (RateLimitError, APIError, APIConnectionError) as e:
                retries += 1
                if retries > max_retries:
                    print(f"Maximum retries reached: {e}")
                    raise e
                
                # Exponential backoff: double the backoff time after each retry
                backoff *= 2
                
                # If we get a specific retry delay from the API
                if hasattr(e, 'retry_after') and e.retry_after:
                    backoff = max(backoff, e.retry_after)
                    
                print(f"Rate limit hit: {e}. Retrying in {backoff} seconds...")
            
            except Exception as e:
                # For non-rate limit errors, just raise them
                print(f"Non-rate limit error: {e}")
                raise e
        
        # If we've exhausted retries
        raise Exception(f"Failed after {max_retries} retries")

    class prompt(BaseModel):
        prompt: str=Field(description="system prompt for assisstant")

    # Use our rate-limit-aware function for API calls
    requirements = make_openai_call(
        model="gpt-4o",
        messages=[{"role": "user", "content": 'write a system prompt to find the {QUERY} in a given provided webpage. Make sure there are no duplicates.'.format(QUERY=QUERY)}],
        response_model=prompt
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
            resp = make_openai_call(
            model="gpt-4o",
            messages=[{'role':"system", "content":prompt1},{"role": "user", "content": cleantext}], response_model=isQuery, max_tokens=4096
            )
            # hasThing = resp.model_dump()['contains_specifics']
            score = resp.model_dump()['score']
            # check = resp.model_dump()[f'is_this_a_{QUERY.replace(" ", "_")}']
            if score > THRESHOLD:
                # print(resp.model_dump()['score'])
                resp = make_openai_call(
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
    
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_url = {executor.submit(process_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result is not None:
                    # Store both properties and source URL
                    all_results.append({'properties': result, 'url': url})
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')
    
    # Deduplicate products based on semantic similarity
    deduplicated_results = []
    found_products = []  # List to track product names we've already found
    sources = {}
    imgs = []
    
    for result in all_results:
        url = result['url']
        for entry in result['properties']:
            product_name = entry[QUERY.replace(' ', '_')]
            
            # Check if this product is similar to any we've already found
            duplicate_found = False
            duplicate_product = None
            
            for existing_product in found_products:
                if is_similar_product(product_name, existing_product):
                    # This is a duplicate
                    duplicate_found = True
                    duplicate_product = existing_product
                    break
            
            if duplicate_found and duplicate_product:
                # Add this URL to the sources for the existing product
                if duplicate_product.lower() in sources:
                    if url not in sources[duplicate_product.lower()]:
                        sources[duplicate_product.lower()].append(url)
            else:
                # This is a new product
                found_products.append(product_name)
                sources[product_name.lower()] = [url]
                imgs.append(scrape_images(product_name))
                deduplicated_results.append(entry)
    
    currentTime = datetime.datetime.utcnow().isoformat()
    
    dymaboDB.put_item(Item={
        'userID': USER, 
        'title': QUERY, 
        'data': json.dumps(deduplicated_results), 
        'timestamp': currentTime,
        'image_urls': json.dumps(imgs), 
        'source_urls': json.dumps(sources), 
        'Count': num_done+1, 
        'visible': True
    })

    response = {"statusCode": 200, 'headers' : {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Credentials': True,}}
    return response


# if __name__ == '__main__':
#     handler('','')



