# Test fixtures

Captured on 2026-10-24 from public PakWheels pages using
`scripts/capture_fixtures.py` and the polite HTTP client:

- `html/pakwheels_list.html`: three real cards from `/used-cars/search/-/`,
  including a Honda BR-V 2024, Suzuki Xbee 2022, and Honda Civic 2011; preserves
  the observed model links and approximate volume counts for scope discovery.
- `html/pakwheels_detail.html`: the first card's BR-V detail page, including
  vehicle schema, features, registration city, and related vehicle schemas.
- `html/pakwheels_missing_fields.html`: a fault-injection derivative of the real
  list fixture with price, schema, and technical attributes removed. This is not
  represented as a separate captured live page.
- `html/pakwheels_model_list.html`: two real cards captured from
  `/used-cars/toyota-corolla/688` on the same date. These cover numeric `data-price`
  attributes on model-search pages, where vehicle JSON can be empty.
- `html/pakwheels_detail_missing_schema.html`: a real Honda City 2019 detail
  page from the same live run, with visible attributes and listing identity but
  no primary vehicle schema. Related cars still have JSON and must be ignored.

Fixtures retain original parser-relevant structure and vehicle values, but discard
contact UI, free-text descriptions, images, scripts other than vehicle JSON,
tracking data, and unrelated markup. Listing identifiers are replaced consistently
within each document with fixture IDs starting at 900001. They are not live URLs.
Raw responses and the database must never be committed.

To deliberately refresh fixtures (changes exact expected test values):

```powershell
.venv/Scripts/python.exe scripts/capture_fixtures.py --contact-email YOUR_EMAIL
```

Default tests block network connections. Opt into a single live check with:

```powershell
$env:TRACKER_CONTACT_EMAIL = "YOUR_EMAIL"
.venv/Scripts/python.exe -m pytest -m live --no-cov
```
