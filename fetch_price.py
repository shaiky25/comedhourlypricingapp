import requests
import boto3
import json

def get_price():
    url = "https://hourlypricing.comed.com/api?type=currenthouraverage"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(url, headers=headers)
    data = response.json()
    return float(data[0]['price'])

def trigger_lambda(price):
    client = boto3.client('lambda', region_name='us-east-1')
    payload = {"current_price": price}
    
    # Trigger the Lambda we built earlier
    client.invoke(
        FunctionName='ComEd_Price_Logger',
        InvocationType='Event', # Async trigger
        Payload=json.dumps(payload)
    )
    print(f"Successfully pushed price {price} to AWS Lambda.")

if __name__ == "__main__":
    current_price = get_price()
    trigger_lambda(current_price)
