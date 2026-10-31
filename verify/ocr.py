"""Image-to-structured receipt fields using an optional vision model.
No key needed to run the dashboard; a configured OPENAI_API_KEY is required for real OCR.
"""
import base64
import hashlib
from pathlib import Path
import json
import os
import urllib.request


def read_receipt(image_bytes: bytes, mime: str) -> dict:
    # Exact-byte demo fixture only. This is a *mock extractor*, not vision OCR.
    # Other images always require the configured real vision model.
    fixture=Path(__file__).resolve().parents[1]/'demo'/'screenshots'/'sharma-payment.png'
    if fixture.is_file() and hashlib.sha256(image_bytes).digest()==hashlib.sha256(fixture.read_bytes()).digest():
        return {'amount':400.0,'reference':'UPI-DEMO-400-1026','timestamp':''}
    key=os.getenv('OPENAI_API_KEY')
    if not key:
        raise RuntimeError('OPENAI_API_KEY is not configured. Configure OCR before verifying actual screenshots.')
    data_uri=f'data:{mime};base64,{base64.b64encode(image_bytes).decode()}'
    payload={'model':os.getenv('PAYTIME_VISION_MODEL','gpt-4o-mini'),'temperature':0,
        'messages':[{'role':'system','content':'Read a payment receipt screenshot. Return ONLY a JSON object with keys amount (number or null), reference (string), timestamp (ISO 8601 string or empty string). Never fabricate missing information. Read any UPI reference or transaction ID accurately.'},
                    {'role':'user','content':[{'type':'text','text':'Extract transaction details from this screenshot.'},{'type':'image_url','image_url':{'url':data_uri}}]}],
        'response_format':{'type':'json_object'}}
    req=urllib.request.Request('https://api.openai.com/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=28) as res:
        response=json.load(res)
    result=json.loads(response['choices'][0]['message']['content'])
    if result.get('amount') is None or not result.get('reference'):
        raise ValueError('Receipt does not clearly show both payment amount and transaction reference.')
    return {'amount':float(result['amount']),'reference':str(result['reference']).strip(),'timestamp':str(result.get('timestamp') or '')}
