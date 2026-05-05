
# Design 2: Hybrid GitHub & DynamoDB Price Logging System

This architecture integrates GitHub Actions with AWS using OIDC (OpenID Connect) to log time-series energy price data into a NoSQL database for historical analysis.

## Objective
To build a secure, credential-free pipeline that archives ComEd price data into DynamoDB every 30 minutes between 5 AM and Midnight.

## Architecture Components
1. **GitHub Actions (Trigger/Producer):** Fetches price from ComEd and invokes the AWS Lambda.
2. **OIDC Federation (IAM):** Allows GitHub to authenticate with AWS without long-term Access Keys.
3. **AWS Lambda (Logger):** Validates and writes data to the database.
4. **Amazon DynamoDB (Storage):** Stores historical price points.

---

## Setup Instructions

### Step 1: Create the DynamoDB Table
1. Open the **DynamoDB Console**.
2. Create a Table:
   - Name: `ComEd_Price_History`
   - Partition Key: `DeviceID` (String)
   - Sort Key: `Timestamp` (Number)
   - Capacity: `On-Demand`.

### Step 2: Configure IAM OIDC for GitHub
1. **IAM > Identity Providers:** Add Provider `token.actions.githubusercontent.com` (Audience: `sts.amazonaws.com`).
2. **IAM > Roles:** Create a role `GitHubAction-ComEd-Trigger`.
3. **Trust Relationship:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringLike": { "token.actions.githubusercontent.com:sub": "repo:USER/REPO:*" }
      }
    }
  ]
}

```
4.Permissions: Attach a policy allowing lambda:InvokeFunction for the Logger Lambda.

### Step 3: Deploy the Logger Lambda

Create a function named ComEd_Price_Logger.

Add IAM permissions for dynamodb:PutItem to the ComEd_Price_History table.

Use the following code (Note: Decimal is required for DynamoDB):

``` python
import boto3, time, json, logging
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)
table = boto3.resource('dynamodb').Table('ComEd_Price_History')

def lambda_handler(event, context):
    price = event.get('current_price')
    if price is None: return {'statusCode': 400}
    
    item = {
        'DeviceID': 'Mundelein_Home',
        'Timestamp': int(time.time()),
        'Price': Decimal(str(price)),
        'DateReadable': time.ctime()
    }
    table.put_item(Item=item)
    return {'statusCode': 200}
  ```
### Step 4: Configure GitHub Repository

In your GitHub Repo, add the following to .github/workflows/check_price.yml:

``` yaml
name: Fetch ComEd Price
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: 'true'
on:
  schedule:
    - cron: '0,30 10-23,0-4 * * *'
  workflow_dispatch:
permissions:
  id-token: write
  contents: read
jobs:
  check-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: pip install requests boto3
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT_ID:role/GitHubAction-ComEd-Trigger
          aws-region: us-east-1
      - run: python fetch_price.py
        ```
### Step 5: The Python Script (fetch_price.py)

Save this in your repository root:

``` python
import requests, boto3, json

def trigger():
    url = "[https://hourlypricing.comed.com/api?type=currenthouraverage](https://hourlypricing.comed.com/api?type=currenthouraverage)"
    price = float(requests.get(url).json()[0]['price'])
    client = boto3.client('lambda', region_name='us-east-1')
    client.invoke(
        FunctionName='ComEd_Price_Logger',
        InvocationType='Event',
        Payload=json.dumps({"current_price": price})
    )

if __name__ == "__main__":
    trigger()
```
