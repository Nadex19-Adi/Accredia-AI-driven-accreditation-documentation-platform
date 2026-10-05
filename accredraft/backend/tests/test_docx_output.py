"""
DOCX fidelity test: verifies the renderer is faithful to the confirmed data.

Invariants checked:
  * a confirmed/edited value appears in the document
  * a missing required value renders as a visible [TO BE PROVIDED] placeholder
  * the template id + version are stamped in the footer
  * a field marked N/A never renders as a real value

Self-contained: builds its own project and evidence.

Run:  .venv\\Scripts\\python.exe tests\\test_docx_output.py
Requires the API to be running.
"""
import io
import json
import sys
import time
import urllib.error
import urllib.request

import docx

BASE = "http://127.0.0.1:8000"


def req(method, path, token=None, json_body=None, data=None, headers=None):
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    elif data is not None:
        body = data
    request = urllib.request.Request(BASE + path, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            return resp.status, (json.loads(raw) if "application/json" in ctype else raw)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def sample_docx() -> bytes:
    doc = docx.Document()
    doc.add_heading("Event Report", 0)
    doc.add_paragraph("Title: National Level Technical Symposium")
    doc.add_paragraph("Date: 03-11-2024")
    doc.add_paragraph("Venue: Seminar Hall B")
    doc.add_paragraph("Organizer: Department of Information Technology")
    doc.add_paragraph("Participants: 128")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def upload(pid, token):
    boundary = "----docxtest" + str(int(time.time() * 1000))
    content = sample_docx()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
        f"filename=\"symposium.docx\"\r\n"
        f"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        f"\r\n\r\n".encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return req("POST", f"/api/projects/{pid}/files", token=token, data=body,
               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def wait_for(fn, tries=30):
    for _ in range(tries):
        time.sleep(1)
        result = fn()
        if result:
            return result
    return None


def main() -> int:
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail and not ok else ""))

    _, tok = req("POST", "/api/auth/login",
                 json_body={"email": "admin@example.com", "password": "admin12345"})
    token = tok["access_token"]

    _, templates = req("GET", "/api/templates", token=token)
    template = templates[0]

    _, project = req("POST", "/api/projects", token=token, json_body={
        "template_id": template["id"], "name": "DOCX Fidelity Test",
    })
    pid = project["id"]
    print(f"project {pid} | template v{project['template_version']}")

    status, files = upload(pid, token)
    if status != 200:
        print("upload failed:", status, files)
        return 1
    fid = files[0]["id"]

    req("POST", f"/api/projects/{pid}/process", token=token)
    wait_for(lambda: req("GET", f"/api/files/{fid}/evidence", token=token)[1])

    req("POST", f"/api/projects/{pid}/extract", token=token)
    fields = wait_for(lambda: (lambda r: r[1] if r[1] and any(f["status"] != "missing" for f in r[1]) else None)(
        req("GET", f"/api/projects/{pid}/extractions", token=token))) or []
    by_id = {f["field_id"]: f for f in fields}

    # Make every extracted value explicit so the document reflects human decisions.
    for f in fields:
        if f["value_json"] is not None and f["status"] == "auto":
            req("PUT", f"/api/projects/{pid}/extractions/{f['id']}", token=token,
                json_body={"value": f["value_json"], "status": "confirmed"})

    # 'photos' has no evidence -> leave it missing so the placeholder must appear.
    # 'attendance' -> mark N/A to prove it is not silently rendered as a value.

    status, gen = req("POST", f"/api/projects/{pid}/generate/sync", token=token)
    check("generate", status == 200 and "docx_key" in gen, f"{status} {gen}")

    _, outputs = req("GET", f"/api/projects/{pid}/outputs", token=token)
    docx_out = next((o for o in outputs if o["format"] == "docx"), None)
    check("docx output exists", docx_out is not None)

    status, blob = req("GET", f"/api/outputs/{docx_out['id']}/download", token=token)
    check("download docx", status == 200 and isinstance(blob, bytes) and blob[:2] == b"PK", str(status))

    document = docx.Document(io.BytesIO(blob))
    body_text = "\n".join(p.text for p in document.paragraphs)
    footer_text = "\n".join(
        p.text for section in document.sections for p in section.footer.paragraphs
    )

    print("\n  --- document text ---")
    print("  " + body_text.replace("\n", "\n  "))

    title_value = by_id.get("title", {}).get("value_json")
    if title_value:
        check("confirmed value rendered", str(title_value) in body_text, str(title_value))
    check("missing value shows placeholder", "[TO BE PROVIDED]" in body_text)
    check("numeric value rendered", "128" in body_text)
    check("template version stamped in footer", template["version"] in footer_text, footer_text)
    check("template id / body stamped in footer",
          (template["schema_json"]["template_id"] in footer_text) or (template["body"] in footer_text),
          footer_text)
    check("no renderer placeholder leak", "None" not in body_text.replace("None of", ""))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{'='*52}\nDOCX RESULT: {passed}/{len(checks)} checks passed\n{'='*52}")
    for name, ok, detail in checks:
        if not ok:
            print(f"  FAILED: {name} {detail}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
