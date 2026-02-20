import os
import json
import requests
import zipfile
import shutil
import logging
import sys
import time
import threading

log = logging.getLogger(__name__)

class Updater:
    def __init__(self, repo_owner, repo_name, current_version_file, project_root):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version_file = current_version_file
        self.project_root = project_root
        self.update_status = {"status": "idle", "progress": 0, "error": None}

    def get_local_version(self):
        try:
            with open(self.current_version_file, "r") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error reading local version: {e}")
            return {"version": "0.0.0"}

    def check_for_update(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data["tag_name"].lstrip("v")
                local_version = self.get_local_version()["version"].lstrip("v")
                
                return {
                    "update_available": latest_version != local_version,
                    "latest_version": latest_version,
                    "local_version": local_version,
                    "release_name": data.get("name"),
                    "changelog": data.get("body"),
                    "published_at": data.get("published_at"),
                    "zipball_url": data.get("zipball_url")
                }
        except Exception as e:
            log.error(f"Error checking GitHub for updates: {e}")
        return None

    def install_update(self, zipball_url, new_version, published_at):
        def _run():
            try:
                self.update_status = {"status": "downloading", "progress": 10, "error": None}
                tmp_dir = os.path.join(self.project_root, "data", "tmp_update")
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir)
                os.makedirs(tmp_dir)

                # Download
                zip_path = os.path.join(tmp_dir, "update.zip")
                r = requests.get(zipball_url, stream=True)
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self.update_status["status"] = "extracting"
                self.update_status["progress"] = 40
                
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(tmp_dir)
                
                # GitHub zipballs have a root folder like "owner-repo-hash"
                extracted_folders = [f for f in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, f))]
                source_dir = os.path.join(tmp_dir, extracted_folders[0])
                
                self.update_status["status"] = "applying"
                self.update_status["progress"] = 70

                # Define what to ignore
                # We don't want to overwrite data, configs, etc.
                ignore_list = [
                    "data",
                    ".venv",
                    "version.json"
                ]
                
                # Also ignore specific files in web_dashboard and bots
                def should_ignore(rel_path):
                    if any(rel_path.startswith(ignored) for ignored in ignore_list):
                        return True
                    if rel_path.endswith(".json") and ("config" in rel_path or "sessions" in rel_path or "users" in rel_path or "admins" in rel_path):
                        return True
                    if rel_path.endswith(".log") or rel_path.endswith(".jsonl"):
                        return True
                    return False

                for root, dirs, files in os.walk(source_dir):
                    rel_root = os.path.relpath(root, source_dir)
                    if rel_root == ".":
                        target_root = self.project_root
                    else:
                        target_root = os.path.join(self.project_root, rel_root)
                    
                    if not os.path.exists(target_root):
                        os.makedirs(target_root)

                    for file in files:
                        source_file = os.path.join(root, file)
                        rel_file = os.path.relpath(source_file, source_dir)
                        target_file = os.path.join(self.project_root, rel_file)
                        
                        if not should_ignore(rel_file):
                            shutil.copy2(source_file, target_file)

                # Update version.json
                with open(self.current_version_file, "w") as f:
                    json.dump({
                        "version": new_version,
                        "release_date": published_at
                    }, f, indent=4)

                self.update_status["status"] = "finished"
                self.update_status["progress"] = 100
                
                # Cleanup
                shutil.rmtree(tmp_dir)
                
                log.info("Update successful. Restarting...")
                time.sleep(2)
                
                # Trigger restart
                os.kill(os.getpid(), signal.SIGTERM)

            except Exception as e:
                log.error(f"Update failed: {e}")
                self.update_status = {"status": "error", "progress": 0, "error": str(e)}

        import signal
        threading.Thread(target=_run).start()

    def get_status(self):
        return self.update_status
