import json
import urllib.request
import urllib.error
import re
import sys
import os

def get_latest_version(package_name):
    # PyPI JSON API
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data['info']['version']
    except urllib.error.HTTPError as e:
        print(f"HTTP Error for {package_name}: {e.code}")
        return None
    except Exception as e:
        print(f"Error fetching {package_name}: {e}")
        return None

def update_requirements_file(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Updating {filepath}...")
    backup_path = filepath + ".bak"
    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Create a backup
    with open(backup_path, 'w') as f:
        f.writelines(lines)
    print(f"Backup created at {backup_path}")

    updated_lines = []
    updates_made = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('-e') or stripped.startswith('-r'):
            updated_lines.append(line)
            continue
        
        # Matches package_name==version or package_name>=version etc
        match = re.match(r'^([a-zA-Z0-9_\-\[\]]+)(==|>=|<=|>|<|~=)(.+)$', stripped)
        if match:
            pkg, op, ver = match.groups()
            # Clean package name from extras like fastapi[standard]
            pkg_clean = re.sub(r'\[.*\]', '', pkg)
            
            print(f"Checking {pkg_clean} (current: {ver})...")
            latest = get_latest_version(pkg_clean)
            if latest:
                if ver != latest:
                    print(f"  -> Found newer version: {latest}")
                    updated_lines.append(f"{pkg}=={latest}\n")
                    updates_made.append((pkg, ver, latest))
                else:
                    print("  -> Already up to date.")
                    updated_lines.append(line)
            else:
                print("  -> Could not fetch version, keeping current.")
                updated_lines.append(line)
        else:
            # If it's just a package name without a version specifier
            pkg_clean = stripped
            latest = get_latest_version(pkg_clean)
            if latest:
                print(f"Checking {pkg_clean} (no version) -> latest: {latest}")
                updated_lines.append(f"{pkg_clean}=={latest}\n")
                updates_made.append((pkg_clean, "none", latest))
            else:
                updated_lines.append(line)

    with open(filepath, 'w') as f:
        f.writelines(updated_lines)

    print(f"\nSuccessfully finished updating {filepath}!")
    if updates_made:
        print("Updates made:")
        for pkg, old, new in updates_made:
            print(f"  - {pkg}: {old} -> {new}")
    else:
        print("No updates needed.")

if __name__ == "__main__":
    target = "requirements.txt"
    if len(sys.argv) > 1:
        target = sys.argv[1]
    update_requirements_file(target)
