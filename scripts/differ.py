import os
import json
import zipfile
from typing import Dict, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import semver

@dataclass
class ModInfo:
    path: str
    version: str
    file_size: int
    sha1: str

class ModpackDiffer:
    def __init__(self, directory: str):
        self.directory = directory
        
    def _extract_index(self, mrpack_path: str) -> dict:
        with zipfile.ZipFile(mrpack_path, 'r') as zip_ref:
            with zip_ref.open('modrinth.index.json') as f:
                return json.loads(f.read().decode('utf-8'))

    def _parse_version(self, filename: str) -> Tuple[str, semver.VersionInfo]:
        base_name = filename.replace('.mrpack', '')
        name_parts = base_name.rsplit(' ', 1)
        
        if len(name_parts) != 2:
            raise ValueError(f"Invalid filename format: {filename}")
            
        name, version = name_parts
        return name, semver.VersionInfo.parse(version)

    def _get_latest_versions(self) -> List[str]:
        mrpack_files = [f for f in os.listdir(self.directory) if f.endswith('.mrpack')]
        
        if not mrpack_files:
            raise FileNotFoundError("No .mrpack files found in directory")
            
        versions_by_name = {}
        for filename in mrpack_files:
            try:
                base_name, version = self._parse_version(filename)
                if base_name not in versions_by_name:
                    versions_by_name[base_name] = []
                versions_by_name[base_name].append((version, filename))
            except ValueError as e:
                print(f"Warning: Skipping {filename} - {str(e)}")
                
        if not versions_by_name:
            raise ValueError("No valid versioned files found")
            
        base_name = list(versions_by_name.keys())[0]
        versions = versions_by_name[base_name]
        
        versions.sort(key=lambda x: x[0], reverse=True)
        return [v[1] for v in versions[:2]]
    
    def _get_base_mod_name(self, mod_name: str) -> str:
        mod_name = mod_name.replace('.jar', '')
        
        import re
        mod_name = re.sub(r'-\d+\.\d+\.\d+\+.*?(?=-|$)', '', mod_name)
        
        mod_name = re.sub(r'-(?:mc)?1\.\d+(?:\.\d+)*', '', mod_name)
        
        mod_name = re.sub(r'-\d+(?:\.\d+)*(?:-[a-zA-Z]+)?$', '', mod_name)
        
        mod_name = re.sub(r'-(?:fabric|forge)$', '', mod_name)
        
        return mod_name

    def _extract_version_from_path(self, path: str) -> str:
        filename = os.path.basename(path).replace('.jar', '')
        
        version_patterns = [
            # Version after MC version: mod-1.20-2.13.47-fabric
            r'-1\.\d+(?:\.\d+)*-(\d+\.\d+\.\d+)',
            # Version before MC version: mod-2.13.47-1.20-fabric
            r'-(\d+\.\d+\.\d+)(?:-1\.\d+)',
            # Version at end: mod-fabric-2.13.47
            r'-(\d+\.\d+\.\d+)$',
            # Version with build/fabric suffix: mod-2.13.47+build.123
            r'-(\d+\.\d+\.\d+)(?:\+[a-zA-Z0-9\.]+)?$',
            # Fallback for any version-like pattern
            r'(?:^|[^0-9])(\d+\.\d+\.\d+)(?:[^0-9]|$)'
        ]
        
        import re
        for pattern in version_patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)
        
        return "unknown"

    def _extract_mod_info(self, index_data: dict) -> Dict[str, ModInfo]:
        mods = {}
        for file in index_data.get('files', []):
            if not file['path'].startswith('mods/'):
                continue
                
            mod_name = os.path.basename(file['path']).replace('.jar', '')
            version = self._extract_version_from_path(file['path'])
            
            mods[mod_name] = ModInfo(
                path=file['path'],
                version=version,
                file_size=file.get('fileSize', 0),
                sha1=file['hashes'].get('sha1', '')
            )
        return mods

    def _extract_version_from_filename(self, filename: str) -> str:
        version_indicators = ['-', '_']
        for indicator in version_indicators:
            if indicator in filename:
                parts = filename.split(indicator)
                for part in parts:
                    if part.replace('.', '').isdigit() or \
                       (part.startswith('v') and part[1:].replace('.', '').isdigit()):
                        return part
        return "unknown"


    def generate_changelog(self) -> str:
        latest_versions = self._get_latest_versions()
        if len(latest_versions) < 2:
            return "Not enough versions to compare"

        new_version = latest_versions[0]
        old_version = latest_versions[1]

        new_data = self._extract_index(os.path.join(self.directory, new_version))
        old_data = self._extract_index(os.path.join(self.directory, old_version))

        new_mods = self._extract_mod_info(new_data)
        old_mods = self._extract_mod_info(old_data)

        # Create dictionaries with base mod names for comparison
        new_mods_base = {}
        old_mods_base = {}
        
        for name, info in new_mods.items():
            base_name = self._get_base_mod_name(name)
            new_mods_base[base_name] = (name, info)
        
        for name, info in old_mods.items():
            base_name = self._get_base_mod_name(name)
            old_mods_base[base_name] = (name, info)

        # Compare mods
        added_mods = []
        removed_mods = []
        updated_mods = []

        # Find updates and additions
        for base_name, (new_name, new_info) in new_mods_base.items():
            if base_name in old_mods_base:
                old_name, old_info = old_mods_base[base_name]
                if (old_info.version != new_info.version and 
                    old_info.version != "unknown" and 
                    new_info.version != "unknown"):
                    updated_mods.append(f"- {base_name}: {old_info.version} → {new_info.version}")
            else:
                mod_entry = f"- {new_name}"
                if new_info.version != "unknown":
                    mod_entry += f" ({new_info.version})"
                added_mods.append(mod_entry)

        # Find removals
        for base_name, (old_name, old_info) in old_mods_base.items():
            if base_name not in new_mods_base:
                mod_entry = f"- {old_name}"
                if old_info.version != "unknown":
                    mod_entry += f" ({old_info.version})"
                removed_mods.append(mod_entry)

        # Generate changelog
        changelog = [f"# Changelog: {new_version} (compared to {old_version})"]
        
        if added_mods:
            changelog.extend([
                "",
                f"## Added Mods ({len(added_mods)})",
                *sorted(added_mods)
            ])
            
        if removed_mods:
            changelog.extend([
                "",
                f"## Removed Mods ({len(removed_mods)})",
                *sorted(removed_mods)
            ])
            
        if updated_mods:
            changelog.extend([
                "",
                f"## Updated Mods ({len(updated_mods)})",
                *sorted(updated_mods)
            ])

        return "\n".join(changelog)


def main():
    script_dir = Path(__file__).parent.parent
    releases_dir = script_dir / 'release'
    docs_dir = script_dir / 'docs'
    
    docs_dir.mkdir(exist_ok=True)
    
    try:
        differ = ModpackDiffer(str(releases_dir))
        changelog = differ.generate_changelog()
        
        latest_versions = differ._get_latest_versions()
        if len(latest_versions) >= 2:
            new_version = latest_versions[0].replace('.mrpack', '')
            changelog_filename = f"changelog_{new_version}.md"
            output_path = docs_dir / changelog_filename
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(changelog)
                
            print(f"\nChangelog has been generated and saved to: {output_path}")
            print("\nChangelog contents:")
            print("-" * 40)
            print(changelog)
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()