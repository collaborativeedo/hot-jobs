# Hot Jobs backlog

What's planned next, and what's been proposed but not yet decided. Newest decisions first.

## Built Oct 29, 2026

- Nightly dead-link check; "Was this job still open?" prompt; one "See a problem?" footer link.
- Case-manager lists: pick up to 12 jobs, copy a link, show a QR code, or print a one-page sheet (prototype for LWP feedback).
- "Fewer barriers" filters: near an LTD bus stop, no degree needed, training provided, fair-chance employer; Spanish interface.
- Staff dashboard: days open, postings added and removed by employer (net-change flags), stated pay by type of work.
- Nightly archive of every posting pulled (data/archive/).
- National Labor Exchange (usnlx.com) added as a nightly source for Lane County; postings QualityInfo already lists are skipped, and NLx's links to employer hiring sites feed the Employer Registry.

## Earlier decisions

- **Drop listings (built Oct 29) whose link no longer works.** Each night, check every listing's link before publishing. A listing whose page returns "not found" or "gone" (404/410), or now redirects to a generic careers or home page, is dropped. Sites that refuse automated visitors (401/403/429) are left alone, not treated as dead. Record the count dropped each night on the staff dashboard. *(Approved by Matt, Oct 29, 2026.)*

## Proposed, not yet decided

- **Resolve dejobs.org pages to the employer's own posting.** About 490 of NLx's 866 Lane postings link to DirectEmployers pages rather than the employer; these are currently treated like job-board links.

- **Weekly quality spot-check.** 25 random listings, about 30 minutes, without slowing registry growth.
- **Public "How Hot Jobs works" page**: no ads, no tracking cookies, no data sold; where listings and pay averages come from; a contact for employer corrections and opt-outs.
- **Employer pages** showing each employer's views and apply clicks, with a way to correct their name or careers page.
- **Training and funding links on listings** (LCC programs, on-the-job training dollars).
- **Rural bus service**: add Link Lane stops to "Near a bus stop" (feed: oregon-gtfs.trilliumtransit.com, lcog-or-us).
- **Move the posting archive out of the repository** once it passes a few hundred MB (it grows about 100-150 MB a year).
