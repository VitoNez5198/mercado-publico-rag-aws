import json
import sys
import time
import urllib.request
from pathlib import Path

pdf_path = Path("samples/pliego_ejemplo_chilecompra.pdf")
api_url = "https://01lzy8hu0c.execute-api.us-east-1.amazonaws.com"

print("=" * 60)
print("TEST LIVE END-TO-END EN AWS")
print("=" * 60)

# 1. Obtener URL prefirmada
payload = {
    "file_name": pdf_path.name,
    "file_size_bytes": pdf_path.stat().st_size
}
req = urllib.request.Request(
    f"{api_url}/licitaciones/upload-url",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.URLError as e:
    print(f"Error solicitando URL: {e}")
    sys.exit(1)

lic_id = data["licitacion_id"]
upload_url = data["upload_url"]
print("1. Presigned URL generada con exito.")
print(f"   ID Asignado: {lic_id}")

# 2. Cargar PDF a S3
with open(pdf_path, "rb") as f:
    pdf_bytes = f.read()

put_req = urllib.request.Request(
    upload_url,
    data=pdf_bytes,
    headers={"Content-Type": "application/pdf"},
    method="PUT"
)

with urllib.request.urlopen(put_req) as resp:
    print(f"2. Archivo subido a S3 con codigo HTTP {resp.status}")

# 3. Polling de estado
print("3. Monitoreando Lambda Ingestion + Bedrock Converse...")
finished = False
for i in range(20):
    time.sleep(3)
    try:
        status_req = urllib.request.Request(f"{api_url}/licitaciones/{lic_id}/status")
        with urllib.request.urlopen(status_req) as s_resp:
            st_data = json.loads(s_resp.read().decode("utf-8"))
            status = st_data.get("status")
            print(f"   [Segundo {(i+1)*3}] Estado en DynamoDB: {status}")
            if status in ["READY", "PARTIAL_SUCCESS", "FAILED"]:
                finished = True
                break
    except urllib.error.URLError as e:
        print(f"   Error consultando estado: {e}")

# 4. Consultar factores
if finished:
    print("\n4. Consultando Factores Auditados (GET /licitaciones/{id}/factores):")
    factors_req = urllib.request.Request(f"{api_url}/licitaciones/{lic_id}/factores")
    with urllib.request.urlopen(factors_req) as f_resp:
        factors_data = json.loads(f_resp.read().decode("utf-8"))
        print(json.dumps(factors_data, indent=2, ensure_ascii=False))
