import os
import sys
from pathlib import Path
from github import Github
from github import Auth
from differ import ModpackDiffer
import argparse

class GitHubReleaser:
    def __init__(self, token: str, repo_name: str):
        auth = Auth.Token(token)
        self.github = Github(auth=auth)
        self.repo = self.github.get_repo(repo_name)
        
    def create_release(self, version: str, changelog: str, mrpack_path: Path) -> None:
        try:
            release = self.repo.create_git_release(
                tag=f"v{version}",
                name=f"Version {version}",
                message=changelog,
                draft=False,
                prerelease=False
            )
            
            release.upload_asset(
                str(mrpack_path),
                label=f"Engineer's Odyssey {version}.mrpack",
                content_type="application/zip"
            )
            
            print(f"Successfully created release v{version}")
            print(f"Release URL: {release.html_url}")
            
        except Exception as e:
            print(f"Error creating release: {str(e)}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Create a GitHub release with changelog')
    parser.add_argument('--token', required=True, help='GitHub personal access token')
    parser.add_argument('--repo', required=True, help='Repository name (username/repo)')
    args = parser.parse_args()

    # Setup paths
    script_dir = Path(__file__).parent.parent
    releases_dir = script_dir / 'release'
    docs_dir = script_dir / 'docs'
    
    docs_dir.mkdir(exist_ok=True)
    
    try:
        differ = ModpackDiffer(str(releases_dir))
        changelog = differ.generate_changelog()
        
        latest_versions = differ._get_latest_versions()
        if len(latest_versions) < 1:
            print("No modpack versions found!")
            sys.exit(1)
            
        new_version = latest_versions[0].replace('.mrpack', '').split(' ')[-1]
        mrpack_path = releases_dir / latest_versions[0]
        
        releaser = GitHubReleaser(args.token, args.repo)
        releaser.create_release(new_version, changelog, mrpack_path)
        
        changelog_path = docs_dir / f"changelog_{latest_versions[0].replace('.mrpack', '')}.md"
        with open(changelog_path, 'w', encoding='utf-8') as f:
            f.write(changelog)
            
        print(f"\nChangelog saved to: {changelog_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()