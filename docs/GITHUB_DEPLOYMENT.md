# Publish SteppeGuard to GitHub and Streamlit Community Cloud

## Current state

As checked on 25 October 2026, this local folder has a Git repository but no commits and no configured remote. No GitHub repository or public app has been created by this preparation. `http://127.0.0.1:8501` is a local preview, not a shareable demo URL.

The project is prepared with `app.py`, pinned runtime dependencies in `requirements.txt`, the existing `.streamlit/config.toml` theme, and both observed data bundles. `.gitignore` excludes the virtual environment, acquisition caches, test output, logs, `.env` files and Streamlit secrets. `.gitattributes` preserves archived data bytes so manifest checksums survive Windows/Linux checkout.

## 1. Create the GitHub repository

Sign in at https://github.com/new and create a repository named **SteppeGuard** under your account.

- Choose **Public** for a straightforward externally accessible demo repository. This publishes the source and bundled satellite/reanalysis evidence. Choose Private if you prefer to restrict source access, and grant Streamlit access to it during deployment.
- Leave **Add a README**, **Add .gitignore**, and **Choose a license** unselected: you are uploading the existing project. A license can be chosen later by the project owner.
- Click **Create repository** and copy its HTTPS URL, such as `https://github.com/YOUR_USERNAME/SteppeGuard.git`.

## 2. Upload the existing project

Open PowerShell and run the following, replacing `YOUR_USERNAME` with the GitHub account or organization that owns the new repository:

```powershell
Set-Location 'C:\Users\w2\Documents\ChatGPT\SteppeGuard'
git add .
git status --short
git commit -m "Prepare SteppeGuard observed case study demo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/SteppeGuard.git
git push -u origin main
```

If `git commit` asks for your identity, set it for this project, then repeat the commit and remaining commands:

```powershell
git config user.name "Your Name"
git config user.email "Your GitHub-verified email or GitHub noreply email"
```

Git may open a browser to sign in when you push. Complete GitHub authentication. Do not enter your GitHub account password as a Git HTTPS password; use the credential-manager browser flow or a GitHub personal access token if your setup explicitly requests one. No GitHub CLI installation is needed.

After pushing, open `https://github.com/YOUR_USERNAME/SteppeGuard`. Confirm that `app.py`, `.streamlit/config.toml`, `requirements.txt`, `data/observed/manifest.json`, and `data/historical/manifest.json` are present. Keep every file in those two data directories, including GeoTIFFs and source records: the app verifies them against the manifests. No file currently requires Git LFS.

## 3. Deploy the web app

GitHub stores the code; **Streamlit Community Cloud runs this Python app**. GitHub Pages does not run Streamlit.

1. Go to https://share.streamlit.io and sign in/connect GitHub. Authorize access to the repository.
2. Click **Create app**, then **Yup, I have an app** if prompted.
3. Set these deployment fields:

   | Field | Value |
   |---|---|
   | Repository | `YOUR_USERNAME/SteppeGuard` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | Python version, under Advanced settings | `3.12` |
   | Secrets | Leave empty |
   | App URL | Choose an available name, for example `steppeguard-akkum` |

4. Click **Deploy**. Community Cloud installs `requirements.txt` and starts the app. It does not need `requirements-data.txt`, provider credentials, or a new data download.
5. Copy the actual `https://…streamlit.app` URL shown after deployment. This is the link to share with MIT Solve reviewers. The example subdomain above is not reserved or already deployed.
6. For an external demo, make the app visible to the intended audience in its sharing settings and open the URL in a private browser window to confirm reviewers can access it.

## 4. Check the deployed demo

- The first tab is **Observed case study**, headed **Observed Historical Case Study — October 2025**.
- The highlight shows NDVI anomaly −15.3%, precipitation 0.4 mm versus 9.3 mm, rainfall anomaly −95.7%, temperature anomaly +0.9°C, and MODERATE stress 54/100.
- The seasonal rule says GRAZE; the recommendation reads **REDUCE GRAZING PRESSURE AND MONITOR**.
- The secondary **September 2026 assessment** remains available, with score 34/100.
- The shared 5 km signal disclaimer, methodology details and CSV downloads are present.

If the app reports an artifact checksum mismatch, check that all data files were pushed unchanged and `.gitattributes` was included before the first commit. Do not remove the checksum validation or delete source records to bypass it. If installation fails, inspect the deployment logs and confirm Python 3.12 was selected.

## Subsequent updates

After editing and checking the app locally:

```powershell
git add .
git commit -m "Update SteppeGuard demo"
git push
```

Community Cloud updates the deployed app from the connected branch. Its archived environmental evidence stays fixed unless you explicitly replace the observation bundles; deployment does not run the acquisition scripts.

Official instructions: [GitHub: upload existing local code](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github) · [Streamlit: deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Streamlit: dependency files](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies).
