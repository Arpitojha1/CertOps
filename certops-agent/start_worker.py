import urllib.request, tarfile, os, shutil, subprocess, sys

url = "https://github.com/smallstep/cli/releases/download/v0.30.6/step_linux_0.30.6_amd64.tar.gz"
urllib.request.urlretrieve(url, "/tmp/step.tar.gz")
with tarfile.open("/tmp/step.tar.gz", "r:gz") as t:
    names = t.getnames()
    t.extractall("/tmp")
src = [n for n in names if n.endswith("/bin/step")][0]
shutil.copy(f"/tmp/{src}", "/usr/local/bin/step")
os.chmod("/usr/local/bin/step", 0o755)
print("step-cli installed", flush=True)

os.execvp("celery", [
    "celery", "-A", "src.tasks.app", "worker",
    "--loglevel=INFO", "--concurrency=2",
])
