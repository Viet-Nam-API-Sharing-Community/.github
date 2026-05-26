# Vietnam API Sharing Community Organization Profile Scaffold

This local folder contains the deployable profile assets for the GitHub organization:

- Organization: `Viet-Nam-API-Sharing-Community`
- Target repository: `Viet-Nam-API-Sharing-Community/.github`
- Target profile file: `.github/profile/README.md`

## Deployment

1. Create or open the organization repository named `.github` under `Viet-Nam-API-Sharing-Community`.
2. Copy the contents of this folder into that repository.
3. Ensure the deployed repository contains:
   - `profile/README.md`
   - `scripts/update_org_profile_metrics.py`
   - `.github/workflows/profile-metrics.yml`
4. Commit and push to the default branch of `Viet-Nam-API-Sharing-Community/.github`.
5. Run the `Update organization profile metrics` workflow manually once, then allow the scheduled workflow to refresh the profile automatically.

## Automation

The profile uses the markers below for generated content:

```md
<!-- ORG-PROFILE-METRICS:START -->
<!-- ORG-PROFILE-METRICS:END -->
```

The included workflow scans public repositories in `Viet-Nam-API-Sharing-Community`, regenerates language coverage, repository signals, and inferred technology capabilities, then commits the updated `profile/README.md`.

## Repository Safety

This folder is intentionally ignored by the personal profile repository via `.gitignore`:

```gitignore
org-profiles/
```

Do not commit this scaffold to the personal `thanhan92-f1/thanhan92-f1` repository. Deploy it only to the organization `.github` repository.
