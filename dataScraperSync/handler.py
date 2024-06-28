import json
import boto3

client = boto3.client('lambda')

def submit_async_task(response):
    client.invoke_async(FunctionName='dataScraper-dev-data-scraper', InvokeArgs=json.dumps(response))

def handler(event, context):
    # print(event)
    # DBresource = boto3.resource("dynamodb")
    # dymaboDB = DBresource.Table('dataSets')
    # eventBody = event['queryStringParameters']
    # QUERY = eventBody['query']
    # TOTAL = int(eventBody['num_result'])
    # USER = eventBody['user']
    headers = {
        'Access-Control-Allow-Origin': '*',  # or specify the allowed origin
        'Access-Control-Allow-Methods': 'POST',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    submit_async_task(event)
    body = {
        "message": "done",
    }
    response = {"statusCode": 200, 'headers': headers, "body": json.dumps(body)}

    return response
