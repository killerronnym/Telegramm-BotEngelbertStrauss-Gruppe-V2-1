import os
import json
import requests
import zipfile
import shutil
import logging
import sys
import time
import threading
import signal

log = logging.getLogger(__name__)

class Updater:
    def __init__(self, repo_owner, repo_name, current_version_file, project_root, github_token=None):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version_file = current_version_file
        self.project_root = project_root
        self.github_token = github_token
        self.update_status = {"status": "idle", "progress": 0, "error": None}

    def _get_headers(self):
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def get_local_version(self):
        try:
            if os.path.exists(self.current_version_file):
                with open(self.current_version_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            log.error(f"Error reading local version: {e}")
        return {"version": "1.0.0", "release_date": "2024-05-20T12:00:00Z"}

    def check_for_update(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if response.status_code == 200:
                releases = response.json()
                if not releases: return {"update_available": False}
                
                data = releases[0]
                latest_version = data["tag_name"].lstrip("v")
                local_data = self.get_local_version()
                local_version = local_data["version"].lstrip("v")
                
                if latest_version != local_version:
                    return {
                        "update_available": True,
                        "latest_version": latest_version,
                        "local_version": local_version,
                        "release_name": data.get("name"),
                        "changelog": data.get("body"),
                        "published_at": data.get("published_at"),
                        "zipball_url": data.get("zipball_url")
                    }
            else:
                log.error(f"GitHub API returned status {response.status_code}")
        except Exception as e:
            log.error(f"Error checking GitHub for updates: {e}")
        return {"update_available": False}

    def install_update(self, zipball_url, new_version, published_at):
        def _run():
            try:
                self.update_status = {"status": "downloading", "progress": 10, "error": None}
                tmp_dir = os.path.join(self.project_root, "data", "tmp_update")
                if os.path.exists(tmp_dir): shutil.rmtree(tmp_dir)
                os.makedirs(tmp_dir, exist_ok=True)

                # Download
                zip_path = os.path.join(tmp_dir, "update.zip")
                r = requests.get(zipball_url, headers=self._get_headers(), stream=True)
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                
                self.update_status["status"] = "extracting"
                self.update_status["progress"] = 40
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                extracted_folders = [f for f in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, f))]
                source_dir = os.path.join(tmp_dir, extracted_folders[0])
                
                self.update_status["status"] = "applying"
                self.update_status["progress"] = 70

                # --- SCHUTZLOGIK FÜR DEINE DATEN ---
                def should_ignore(rel_path):
                    # 1. Kompletter Daten-Ordner (Dort liegen deine Quizfragen, Logs, Avatare!)
                    if rel_path.startswith("data/") or rel_path == "data": return True
                    # 2. Python Environment & Logs
                    if rel_path.startswith(".venv/") or rel_path == ".venv": return True
                    if rel_path.endswith(".log") or rel_path.endswith(".jsonl"): return True
                    # 3. ALLE Konfigurationsdateien (.json) schützen, damit User-Settings bleiben
                    if rel_path.endswith(".json"): return True
                    # 4. Git-Dateien
                    if rel_path.startswith(".git/"): return True
                    return False

                for root, dirs, files in os.walk(source_dir):
                    rel_root = os.path.relpath(root, source_dir)
                    target_root = self.project_root if rel_root == "." else os.path.join(self.project_root, rel_root)
                    
                    if not os.path.exists(target_root):
                        os.makedirs(target_root, exist_ok=True)

                    for file in files:
                        source_file = os.path.join(root, file)
                        rel_file = os.path.relpath(source_file, source_dir)
                        target_file = os.path.join(self.project_root, rel_file)
                        
                        if not should_ignore(rel_file):
                            shutil.copy2(source_file, target_file)

                # Version lokal aktualisieren
                with open(self.current_version_file, "w") as f:
                    json.dump({"version": new_version, "release_date": published_at}, f, indent=4)

                self.update_status["status"] = "finished"
                self.update_status["progress"] = 100
                time.sleep(2)
                
                # Neustart
                os.kill(os.getpid(), signal.SIGTERM)

            except Exception as e:
                log.error(f"Update failed: {e}")
                self.update_status = {"status": "error", "progress": 0, "error": str(e)}

        threading.Thread(target=_run, daemon=True).start()

    def get_status(self):
        return self.update_status
