# Design 1: Native AWS ComEd Price Alerting System

This architecture provides a fully managed, serverless solution for monitoring ComEd hourly energy prices and sending email notifications when prices drop below a specified threshold. It is optimized for zero-cost operation within the AWS Free Tier.

## Objective
To receive real-time email alerts in Mundelein, IL, when electricity prices are "cheap," while ensuring only one alert is sent per hour and the system pauses at night.

## Architecture Components
1. **Amazon EventBridge (Scheduler):** Triggers the system every 30 minutes from 5 AM to 12 AM CST.
2. **AWS Lambda (Checker):** Executes Python logic to fetch price and evaluate thresholds.
3. **AWS Systems Manager (SSM) Parameter Store:** Persists the state (last alert time/snooze status).
4. **Amazon SNS (Simple Notification Service):** Dispatches the email alert.

---

## Setup Instructions

### Step 1: Create the SNS Topic
1. Open the **Amazon SNS Console**.
2. Create a **Standard Topic** named `ComEd_Price_Alerts`.
3. Create a **Subscription**:
   - Protocol: `Email`.
   - Endpoint: Your email address.
4. Confirm the subscription via the link sent to your email.
5. Copy the **Topic ARN**.

### Step 2: Initialize State in SSM
1. Open **Systems Manager > Parameter Store**.
2. Create a Parameter:
   - Name: `/comed/state`
   - Type: `String`
   - Value: `{"last_hour": "", "snooze_day": ""}`

### Step 3: Configure IAM Permissions
Create an IAM Execution Role for your Lambda with the following inline policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:PutParameter",
                "sns:Publish",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "*"
        }
    ]
}

```
### Step 4: Deploy the Lambda Function

Create a function named ComEd_Price_Checker (Runtime: Python 3.12).

Set Timeout to 15 seconds in Configuration > General settings.

Add Environment Variables:

PRICE_THRESHOLD: e.g., 3.0

SNS_TOPIC_ARN: (The ARN from Step 1)

Use the following code:

```python
import json, urllib3, logging, boto3, os
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ssm, sns, http = boto3.client('ssm'), boto3.client('sns'), urllib3.PoolManager()

def lambda_handler(event, context):
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    current_hour_key, today_str = now.strftime("%Y-%m-%d-%H"), now.strftime("%Y-%m-%d")
    threshold = float(os.environ.get('PRICE_THRESHOLD', 3.0))
    topic_arn, param_name = os.environ.get('SNS_TOPIC_ARN'), "/comed/state"

    res = ssm.get_parameter(Name=param_name)
    state = json.loads(res['Parameter']['Value'])

    if state.get("snooze_day") == today_str:
        return {"status": "snoozed"}

    url = "[https://hourlypricing.comed.com/api?type=currenthouraverage](https://hourlypricing.comed.com/api?type=currenthouraverage)"
    response = http.request('GET', url, timeout=5.0)
    price = float(json.loads(response.data.decode('utf-8'))[0]['price'])

    if price < threshold:
        if state.get("last_hour") != current_hour_key:
            message = f"ComEd Price Alert: {price} cents/kWh. Snooze: {os.environ.get('SNOOZE_API_URL')}"
            sns.publish(TopicArn=topic_arn, Message=message, Subject="Cheap Power Alert")
            state["last_hour"] = current_hour_key
            ssm.put_parameter(Name=param_name, Value=json.dumps(state), Type='String', Overwrite=True)
    return {"status": "processed", "price": price}

```
### Step 5: Schedule with EventBridge

Open EventBridge > Scheduler.

Create a schedule named ComEd_30min_Check.

Cron Expression: cron(0,30 10-23,0-4 * * ? *) (Covers 5 AM - 12 AM CST).

Target: ComEd_Price_Checker.

