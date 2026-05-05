import json
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo

ssm = boto3.client('ssm')
PARAM_NAME = "/comed/state"

def lambda_handler(event, context):
    tz = ZoneInfo("America/Chicago")
    today_date = datetime.now(tz).strftime("%Y-%m-%d")
    
    # 1. Get existing state
    try:
        res = ssm.get_parameter(Name=PARAM_NAME)
        state = json.loads(res['Parameter']['Value'])
    except:
        state = {"last_hour": ""}

    # 2. Set the snooze for today
    state["snooze_day"] = today_date
    
    ssm.put_parameter(
        Name=PARAM_NAME, 
        Value=json.dumps(state), 
        Type='String', 
        Overwrite=True
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": f"<h1>Snoozed!</h1><p>Alerts for {today_date} have been disabled.</p>"
    }