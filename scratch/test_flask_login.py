import os
os.environ['CLOUD_MODE'] = 'true'
import sys
sys.path.insert(0, os.path.abspath('gestao_stae'))
from app import app

with app.test_client() as client:
    resp = client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    print("Status:", resp.status_code)
    print("Headers:", resp.headers)
    
    # Try to access index
    resp2 = client.get('/')
    print("Index Status:", resp2.status_code)
    print("Index Headers:", resp2.headers)
