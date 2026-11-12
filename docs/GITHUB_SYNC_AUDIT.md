# GitHub synchronisation audit (2026-11-12)

This is a check of whether everything that belongs to OSRIP on this computer is on GitHub
(`azanalmasaoudi-cyber/OSRIP`), and of what is left out on purpose.

**Result:** apart from one documentation commit (see "GitHub branches not in main"), every project
file was already on GitHub. That commit had reached GitHub on another branch but never `main`;
branch `sync/github-audit-2026-11-12` brings it into `main`. Nothing failed to upload.

## Repository and access

- **Remote:** `origin` is `https://github.com/azanalmasaoudi-cyber/OSRIP.git` for both fetch and push.
- **Default branch:** `main`. The repository is public.
- **Credential:** the stored Git credential has push and admin rights on the repository.
- **Errors:** a test push and the real pushes went through, with no authentication or permission
  errors.

## The local repository (`Desktop\OSRIP`)

| Check | Finding |
|---|---|
| `git status` | `main`, clean, equal to `origin/main` (`80660b9`) |
| Tracked files | 965 on `main` |
| Modified or untracked files | None |
| Commits not pushed | None. Every commit on all 26 local branches is on GitHub |
| Branches with no upstream | `feature/username-accounts-fast-research` and `redesign/omani-decision-platform`. Their commits are already in `main` |
| Stashes | None |

## Other working folders of the same repository (Git worktrees)

| Folder | Finding |
|---|---|
| `Desktop\OSRIP-redesign`, `OSRIP-sector-images`, `OSRIP-upgrade` | Clean; their branches are on GitHub |
| `Desktop\OSRIP-premium` | 19 staged files (design packages, booklet ZIPs, ICDL PDF). All 19 are byte-identical to the files `main` received in PR #18 |
| `OSRIP-fix-periods`, `OSRIP-v0-dashboard` | Folders no longer exist. Git still lists them as worktrees that can be pruned; their branches are on GitHub |

## GitHub branches not in `main`

| Branch | Commits not in `main` | What happened |
|---|---|---|
| `feature/osrip-platform-upgrade` (open PR #4) | 1: `f65210b`, docs only | Merged into the sync branch: `docs/PLATFORM_UPGRADE.md`, the API table for roles, groups, monitoring and the decision brief, and its test-results entry. The code they describe (migration 0026, `admin.py`, `analysis.py`) is already in `main`. Once the sync branch is merged, GitHub will show PR #4 as merged |
| `v0/osrip-dashboard-redesign-8aa659ba` | 2, made by v0 | No net change: the second commit reverses the first line for line. Nothing to bring over |

## Left out on purpose (`.gitignore`)

| What | Why |
|---|---|
| `backend/.env`, `deploy/.env` | Real configuration and secrets. The `.env.example` files, with placeholders only, are committed |
| `frontend/node_modules/`, `backend/.venv/` | Dependencies, rebuilt with `npm ci` and `pip install -r requirements.lock` |
| `frontend/dist/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`, `obj/`, `test-results/`, `playwright-report/` | Generated build and test output |
| `.vs/`, `docs/.vscode/`, `/.claude/` | Editor and tool state with paths on this computer |
| `/docs/Downloads/` | A copy of a personal Downloads folder (coursework, installers). Not part of OSRIP |
| `/OSRIP/` | The September foundation prototype, 0.1.0 (97 source files), replaced by the current project; 66 of its files exist in no version on GitHub. Kept on this computer only |
| `/Web.config` | Unused leftover from an old web project template |

## Copies outside the repository

| Location | Finding |
|---|---|
| `Desktop\OSRIP-recovered\B-redesign-2026-11-01` | 833 of 833 files are on GitHub |
| `Desktop\OSRIP-recovered\A-local-uncommitted-2026-11-01` | 838 of 841 files are on GitHub. The other 3:<ul><li>earlier drafts of `backend/tests/test_username_accounts_integration.py` and `frontend/e2e/entrance.spec.ts`, both on `main` in their later form;</li><li>`uncommitted-changes.patch`, a recovery copy of that same work.</li></ul> |
| `Desktop\OSRIP_Premium_Four_Separate_Sector_Images.zip` | Its five files are identical to `docs/OSRIP_Premium_Sector_Cards/` |
| `Desktop\New Folder\OSRIP` | Git data only; all 19 of its commits are on GitHub |

## Secret check

All 965 files on `main` and the merged documentation were scanned for credential-shaped strings.
The scan looked for:
- API keys and tokens;
- private keys;
- URLs with a password;
- assigned passwords and secrets.

No credential was found. Four matches were checked by hand:
- three connection-string templates that insert the password at run time (`devdb.py`, `serve_public.py`, `start_osrip.py`);
- one password marked test-only in an integration test.

No `.env`, key, certificate or database file is tracked.

## Why files can seem to be missing on GitHub

- **Other branches:** GitHub's front page shows `main`. Work on other branches appears there only
  once it is merged; the platform-upgrade documentation was such a case.
- **Ignored files:** the files listed under "Left out on purpose" never appear, by design.
