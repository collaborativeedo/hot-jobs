# Lane County Hot Jobs

A public beta index of open jobs in Lane County, Oregon, built by Collaborative Economic Development Oregon (CEDO) with Lane Workforce Partnership. Partner websites show it with one line of code, and it refreshes itself every night.

## How it works

1. **Every night** a scheduled GitHub Action runs `scripts/refresh.py`. It reads every Lane County posting from the [QualityInfo Job Finder](https://www.qualityinfo.org/jfind) (Oregon Employment Department), removes duplicates, and tags each job with its type of work, industry and employer.
2. The widget's list, `docs/jobs.json`, holds postings up to 14 days old with a direct link (WorkSource Oregon or the employer's own hiring site), newest first. Indeed and SimplyHired reposts are left out because they are often expired or sit behind a "confirm you're human" check; both settings are at the top of `scripts/refresh.py`. Every posting still counts toward the employer lists below. `data/state.json` keeps the date each job was first and last seen; a job counts as closed after it misses three nightly runs.
3. The run also keeps a record of every employer it has seen (`data/employers.json`) and publishes two lists for the Employer Registry Google Sheet: `docs/employers.csv` (each employer, its hiring platform and careers page when a posting reveals them, open postings, first and last seen) and `docs/to-trace.csv` (postings that do not name the employer).
4. GitHub Pages publishes the `docs` folder. `docs/widget.js` is the embeddable widget, and it reads `jobs.json` from the same address.
5. A partner pastes one line into their site, and every update here reaches every partner site on the next page load.

## Direct links from employers' hiring systems

The run grows its own list of employers to pull from directly, with no review step:

1. When a QualityInfo posting links to an employer's hiring system (Workday, Oracle Recruiting, UKG), the run saves that system to `data/sources.json`. PeaceHealth's careers site is included from the start.
2. Every night it pulls each saved system's Lane County openings straight from the employer, so the widget links to the employer's own posting. A direct posting replaces the QualityInfo copy of the same job, and any WorkSource Oregon copy with the same employer, title and city.
3. `docs/sources.csv` lists every system, how many Lane openings it had last night, and whether it was pulled. A site that actively refuses automated requests (a 401, 403 or 429 answer) is recorded and left alone; the run never logs in, solves a challenge, or disguises itself as a person.
4. Employers whose postings live on their own careers site are named from the site's own name, cached in `data/domain-names.json`. Known careers domains and hiring-platform account names are in `scripts/rules.py`.

Public employers on NEOGOV (governmentjobs.com and schooljobs.com: Lane County, the City of Eugene, school districts and others) are pulled with one location search around Eugene, Florence, Oakridge and Cottage Grove.

## Add the widget to a website

```html
<script src="https://collaborativeedo.github.io/hot-jobs/widget.js" defer></script>
```

Optional settings on the same tag:

| Setting | Example | Effect |
| --- | --- | --- |
| `data-type` | `Healthcare & human services` | Starts filtered to a type of work (`A|B` for several) |
| `data-workplace` | `Healthcare` | Starts filtered to a kind of workplace (`A|B` for several) |
| `data-hours` | `Full-time` | Starts filtered to Full-time, Part-time or Temporary or seasonal |
| `data-city` | `Florence` | Starts filtered to one city |
| `data-title` | `Open healthcare jobs` | Changes the heading |
| `data-target` | `jobs-box` | Draws inside an existing element with that id |

In WordPress, use a Custom HTML block. Adding scripts usually requires an administrator account.

## One-time setup

1. Push this repository to GitHub as a **public** repository named `hot-jobs`.
2. In the repository, open **Settings > Pages** and set **Source** to **GitHub Actions**.
3. Open **Actions > Refresh and publish > Run workflow** to run the first refresh by hand.
4. The widget is then live at `https://collaborativeedo.github.io/hot-jobs/widget.js`, and a demo page at `https://collaborativeedo.github.io/hot-jobs/`.

## Feeding the Employer Registry

In the registry Google Sheet, add a tab with this formula in cell A1:

```
=IMPORTDATA("https://collaborativeedo.github.io/hot-jobs/employers.csv")
```

The tab refreshes itself, so new employers appear without anyone copying them. Staff review them and move them into the Employers tab, where people's edits are never overwritten. A second tab with `to-trace.csv` lists the postings whose employer still needs to be identified by hand.

## What each job shows

- **Employer**: from the hiring system, the posting link, the careers site's own name, or the posting text. When none of these names it, the widget says "Employer not listed".
- **Pay**: the pay stated in the posting when there is one. Otherwise the average pay for that occupation in Lane County (or Oregon) from the Oregon Employment Department wage figures that QualityInfo shows next to each listing, labeled as an average, not an offer.
- **Hours**: full-time, part-time or temporary/seasonal when the hiring system, the WorkSource listing page or the posting text says so; otherwise "Not stated".
- **Where you'd work**: the kind of workplace, from the employer. Filters combine as "any of" within a group and "all of" across groups, so *Finance & accounting* plus *Healthcare* finds finance jobs at healthcare employers.
- **View and apply**: opens the original posting, with a note on where it leads.

WorkSource Oregon listing pages are read for hours, pay and the full description; the run never answers their contact-information question.

## Editing the tagging rules

All rules live in `scripts/rules.py`: type of work by occupation code, industries by keywords, and employer names matched from posting text. Each employer rule was checked against a real posting. Add or fix a rule, commit, and the next refresh uses it.

## Ground rules for data collection

- The script identifies itself as CEDO's job index and pauses one second between requests.
- robots.txt is treated as advisory (CEDO decision, October 2026); the switch is `RESPECT_ROBOTS` in `scripts/direct.py`. Active blocks are always respected.
- OED's own job site (`secure.emp.state.or.us`) does not allow automated access, so the script never visits it. It only records the links QualityInfo lists.
- Indeed and SimplyHired are never crawled directly. Their postings appear only where QualityInfo lists them.

## Test offline

```bash
pip install -r requirements.txt
python scripts/refresh.py --fixture tests/fixture_page.html
```

That run writes to `tests/out/` and leaves the real data alone.
