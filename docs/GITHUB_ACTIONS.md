# Run it in GitHub Actions (cloud)

This project contains `.github/workflows/scrape.yml`. The workflow runs only when manually started.

1. Create a private repository on GitHub.
2. Push the project contents (including the hidden `.github` directory) to the repository. One way, from PowerShell in the extracted project folder, is:

   ```powershell
   git init -b main
   git add .
   git commit -m "Add Scrapling cloud crawler"
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
   git push -u origin main
   ```

   Replace the remote URL with your private repository URL. GitHub Desktop is also fine.
3. Open **Actions** and enable workflows if GitHub prompts you.
4. Select **Scrapling cloud crawl**.
5. Click **Run workflow**.
6. Choose the crawl limits and fetch mode. Start conservatively.
7. Download the generated workflow artifact after the run completes.

The artifact contains the `output/`, `exports/`, and `logs/` folders. Download the `_scrape_bundle.zip` inside `exports/` for one portable data archive.

The workflow uses GitHub-hosted runners and GitHub's artifact retention. Repository visibility should be private because crawl archives may contain copied page HTML. Never commit credentials or personal browser cookies.
