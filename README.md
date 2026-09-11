# Warrnambool Camera Club Member Gallery

This package contains the first complete GitHub Pages version of the WCC member competition gallery.

## Included data

The supplied historical import contains:

- 609 regular competition images
- 16 photographers
- 9 Image of the Year award/placegetter images
- 0 unresolved review records

The normal member galleries deliberately exclude Image of the Year resubmissions. The separate IOTY section contains only year-end placegetters/awards.

## Repository layout

- `site/` - the public GitHub Pages site
- `site/data/photos.json` - regular member-gallery images
- `site/data/ioty.json` - IOTY award images
- `site/data/processed.json` - result posts already imported
- `site/data/member_ids.json` - MyPhotoClub image-folder/member mapping
- `site/data/review.json` - records requiring manual review
- `scripts/wcc_importer.py` - MyPhotoClub importer
- `.github/workflows/gallery.yml` - update + GitHub Pages deployment workflow

## First GitHub setup

1. Create or choose the GitHub repository that will host the gallery.
2. Copy the contents of this package into the repository root and push to `main`.
3. In GitHub open **Settings > Pages**.
4. Under **Build and deployment**, set **Source** to **GitHub Actions**.
5. Open **Actions** and run **Update and deploy member gallery** if the first push has not already deployed it.

The workflow uses the current GitHub Pages custom-workflow model: it uploads the `site` directory as the Pages artifact and deploys it with the `github-pages` environment.

## Ongoing updates

The workflow checks MyPhotoClub automatically once per month. Normal updates scan page 1 only and skip result posts already recorded in `processed.json`.

There is also a manual **Run workflow** button. Leave **full_scan** off for a normal update. Turn it on only when you deliberately want to inspect all four historical listing pages.

If nothing new is published, the importer changes nothing.

If the importer creates anything in `review.json`, the GitHub workflow stops before publishing or committing the new data. This prevents an unresolved photographer/title parse from silently entering the live gallery.

## New members

The importer learns the MyPhotoClub CloudFront folder ID used by known photographers. A completely new photographer may initially be placed in `review.json` because the importer cannot safely determine where the image title ends and the photographer name begins. That is intentional.

When that happens, add the photographer's exact displayed name to `KNOWN_MEMBERS` in `scripts/wcc_importer.py`, clear the resolved review record, and run the workflow again.

## Local preview

Because the site loads JSON with `fetch()`, do not simply double-click `site/index.html`.

On Windows, double-click:

`preview_local.bat`

It starts a small local web server and opens the gallery at `http://localhost:8000/`.

## Gallery behaviour

- small MyPhotoClub images are used in the browsing grid
- clicking a photograph loads its `-large.jpg` version in a floating viewer
- left/right arrows and keyboard arrow keys move through the current gallery
- Escape closes the viewer
- member, competition and award filters are available
- the IOTY section is separate from the normal member galleries


## v2 filtering changes

The gallery no longer exposes inconsistent raw competition titles in a single dropdown.

Competition browsing is now normalized into:
- Year
- Month
- Set Subject
- Photographer
- Result

The month is taken from the competition name rather than the result-post publication date, because some results are published in the following month. The year comes from the explicit competition title where available, otherwise the result-post year is used.

Set Subject is derived from the set-subject section names, so a competition such as the November Interclub can expose multiple set subjects independently.


## v3 faceted filters

All gallery filters now constrain one another.

Examples:
- choosing 2026 shows only months and set subjects that exist in 2026
- choosing a set subject limits Year and Month to only the competitions where that subject occurred
- choosing a photographer limits the other filters to values available for that photographer
- changing Result also constrains the available member/year/month/subject choices

Each dropdown is calculated from the current selections in all the *other* filters. This is standard faceted-search behaviour and prevents users selecting combinations that can never return an image.


## v4 display-title cleanup

The original title from MyPhotoClub is retained unchanged in `photos.json`.

For display in the web page only:
- a leading `S_###_` or `O_###_` is removed
- remaining underscores are converted to spaces
- repeated whitespace is collapsed

Example:
`S_003_The_One_Among_Many` displays as `The One Among Many`.

This keeps the source data intact while presenting clean human-readable titles.


## v5 title-prefix handling

Display-title cleanup now accepts the variations produced by MyPhotoClub, including:

- `S_003_Title`
- `O_003_Title`
- `S 003 Title`
- `O 003 Title`
- `003_Title`
- `003 Title`

Only a three-digit number at the very start (optionally preceded by S or O) is removed.
Numbers occurring later in a legitimate title are left untouched.
