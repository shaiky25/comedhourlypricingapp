import json
import urllib3
import logging
import boto3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients outside the handler (Best Practice!)
ssm = boto3.client('ssm')
sns = boto3.client('sns')
http = urllib3.PoolManager()

def lambda_handler(event, context):
    # 1. Setup Context
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    current_hour_key = now.strftime("%Y-%m-%d-%H")
    today_str = now.strftime("%Y-%m-%d")
    
    # Configuration
    threshold = float(os.environ.get('PRICE_THRESHOLD', 3.0))
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    snooze_url = os.environ.get('SNOOZE_API_URL', 'No URL Provided')
    param_name = "/comed/state"

    # Safety check: Prevent timeout if ARN is missing
    if not topic_arn:
        logger.error("SNS_TOPIC_ARN is missing from Environment Variables!")
        return {"status": "error", "message": "Missing SNS ARN"}

    # 2. Check State in SSM
    try:
        res = ssm.get_parameter(Name=param_name)
        state = json.loads(res['Parameter']['Value'])
    except Exception as e:
        logger.warning(f"Initializing state. Parameter might not exist yet: {e}")
        state = {"last_hour": "", "snooze_day": ""}

    if state.get("snooze_day") == today_str:
        logger.info(f"Snoozed for {today_str}. Exiting.")
        return {"status": "snoozed"}

    # 3. Fetch Price
    try:
        url = "https://hourlypricing.comed.com/api?type=currenthouraverage"
        # We know currenthouraverage works!
        response = http.request('GET', url, timeout=5.0)
        data = json.loads(response.data.decode('utf-8'))
        price = float(data[0]['price'])
        logger.info(f"Price: {price}, Threshold: {threshold}")
    except Exception as e:
        logger.error(f"API Fetch failed: {e}")
        return {"status": "error", "message": "API Failure"}

    # 4. Logic & Alert
    if price < threshold:
        if state.get("last_hour") == current_hour_key:
            logger.info(f"Already alerted during hour {current_hour_key}. Skipping.")
        else:
            logger.info("Attempting to publish SNS alert...")
            message = (
                f"ComEd Price Alert: {price} cents/kWh.\n\n"
                f"Threshold: {threshold} cents.\n\n"
                f"Snooze alerts for the rest of today: {snooze_url}"
            )
            sns.publish(TopicArn=topic_arn, Message=message, Subject="Cheap Power Alert")
            
            # Update state
            state["last_hour"] = current_hour_key
            ssm.put_parameter(Name=param_name, Value=json.dumps(state), Type='String', Overwrite=True)
            logger.info("Success: Alert sent and state saved to SSM.")
    
    return {"status": "processed", "price": price}