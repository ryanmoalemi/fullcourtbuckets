# Data dictionary: FCB WNBA ownership dataset (v3)

Data version: v3 · Data through: Oct 19, 2026 (PT) · License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), credit Full Court Buckets and link https://fullcourtbuckets.com/wnba/owners/.
Source of truth: the CSVs in `data/wnba/owners/`. `automation/build_owners.py` generates every count, table and finding on the page from them; nothing on the page is typed in by hand.
Corrections, media and data questions: ryan@fullcourtbuckets.com (general: hello@fullcourtbuckets.com).

## Conventions used in every file
- **IDs** are stable slugs (`rel-…`, `ent-…`, `txn-…`, `fac-…`, `obs-…`, `val-…`, `team-…`, `src-…`). Permalinks use IDs, never ranks or dollar figures.
- **Dates** are ISO. `date_precision` says day, month or year; missing days are never invented.
- **Unknown is never zero.** A blank amount always comes with a status field that says why (not disclosed, not established, disputed, bundled).
- **Source types:** primary filing · primary document (municipal) · primary record (registry) · official announcement · official publication · original journalism · publisher estimate · FCB calculation · none located.
- **Evidence status:** sourced · report only · primary not located · disputed.
- **Current status:** current as of cited evidence (evidence dated in the last 24 months) · current (controlling owner corroborated by a 2026 report) · historically disclosed; current status not reconfirmed · future team: announced ownership.
- **Money:** USD millions, nominal unless the column says 2026 dollars. Arithmetic runs at full precision and is displayed to one decimal.

## ownership.csv: current ownership summary (18 rows: 15 active teams, 3 announced) · 12 fields
team_id · team · scope (active / future) · team_page (existing FCB slug) · controlling_owner · controlling_owner_source_url · controlling_owner_evidence · governor (currently "not yet sourced" for every team) · nba_relationship_current · nba_relationship_at_2026_05_04 (the snapshot used for valuation comparisons) · facility_project_ids · last_verified_at.
NBA relationship values: shared controlling ownership (evidence) · other affiliation (e.g., minority/parent role) · no qualifying shared-control relationship identified · unclear.

## investors.csv: publicly disclosed ownership and investor register (62 rows) · 22 fields
| Field | Definition |
|---|---|
| relationship_id | One person/entity–team relationship |
| person_or_entity_id | Counts unique people separately from relationships |
| entity_type | person · family group · institution · unnamed group |
| team, team_scope | Team; active or future |
| investor | As named in the source |
| role_as_described | The source's own words (principal, minority, partner, alternate governor…). Governor titles never create equity |
| relationship_type | team ownership as described (legal structure not documented) · indirect via documented parent · unnamed investor group |
| parent_path | Parent entity when the stake is in a parent (BSE Global, Monumental) |
| disclosed_stake | Only when disclosed; parent percentages are not converted into franchise percentages |
| effective_date, date_precision | Approval date if published, else announcement date |
| last_evidence_date | Date of the newest document we cite for this relationship |
| last_verified_at | Date FCB last checked it |
| current_status | See conventions |
| background_tags | Semicolon list; tags can overlap and are never summed as exclusive groups. "former pro athlete" = played professionally |
| background_basis | stated in cited document · FCB classification from public biography (source not linked) |
| evidence_status, source_type, primary_source_url | See conventions |
| counts_toward_active_findings | yes only for named investors at active teams |
| notes | Caveats |
League-level investors (the 2022 capital raise) are not in this file and never enter franchise counts.

## entities.csv: documented legal entities (24 rows) · 14 fields
entity_id · team · entity · documented_role (exactly what the record shows: issuer, buyer entity, lease tenant, foreign registration…) · jurisdiction_of_formation · registration_to_do_business (kept separate) · record_type · record_id · record_date · primary_source_url · status (found / not found) · last_verified_at · limitation (a registry entry is not proof of ownership or control) · notes.

## transactions.csv: franchise transaction ledger (22 rows) · 27 fields
transaction_id (one per deal; announcement, approval and closing are milestone columns, not separate rows) · year · franchise (relocations shown as A -> B) · seller · buyer · transaction_type (control sale · control sale (with relocation) · expansion admission fee · bundled acquisition (with NBA team) · not a WNBA transaction (context)) · announcement_date · approval_date · closing_date · amount_usd_m (blank for bundles) · bundled_amount_usd_m · currency · amount_status (disclosed in filing · disclosed in seller release · reported · disputed · not disclosed in seller filing · not established from available sources · bundled; no WNBA allocation) · consideration_scope (cash/note/installments/total-commitment) · event_source_url / event_source_type (the document that establishes the deal) · amount_source_url (the document that establishes the number; often journalism) · cpi_series · cpi_source_period · cpi_source_value · cpi_target_period · cpi_target_value · amount_2026_usd_m · eligible_for_summaries · exclusion_reason · last_verified_at · notes.

**Inflation.** Adjusted = nominal × target index ÷ source index. BLS CPI-U, U.S. city average, all items, NSA (CUUR0000SA0), from api.bls.gov on Oct 19, 2026. Source period = the deal year's annual average (matches BLS published averages 2002–2024). 2025 = 11-month average (no October 2025 index was published). Target = January–September 2026 average, 332.243 (latest month September 2026, 336.940). This measures purchasing power, not investor returns. Disputed and bundled amounts are excluded from summaries. Expansion fees and control sales are never combined in one statistic.

## facility_projects.csv: one row per project (11 rows) · 17 fields
project_id · project_name · linked_teams (a shared campus is one project with several teams) · use_classification (WNBA-exclusive · WNBA practice facility within a mixed-use campus · shared sports facility · unknown) · project_type · asset_owner_operator (only if documented) · location · delivery_status (announced · approved · under construction · under construction (delayed) · under construction (status disputed) · operational · canceled · unknown) · status_as_of · announced · original_target · revised_target · operational_date · floor_area_sqft · floor_area_scope (WNBA portion or whole campus) · primary_source_url · notes.
Teams with no project (Lynx and Mystics share facilities; Dream uses a partner facility; Sun has none announced) appear in ownership.csv with an empty facility_project_ids.

## facility_financials.csv: money observations (18 rows) · 14 fields
observation_id · project_id · amount_usd_m · precision · observation_type (announced/reported project cost · original budget · revised budget · documented private funding commitment · reported private funding · public funding · public support (in kind)) · funding_type · funder · status (stated · reported · authorized…) · observation_date · source_url · source_type · total_bucket · supersedes_or_note · notes.
**Total buckets, never added to each other:** A = announced budget of unique projects (revised budget replaces the original; shared and scope-unresolved projects shown separately) · B = documented private funding · C = public funding/support, by type and status (never summed into one subsidy figure) · D = verified expenditure (no records yet). A project budget is not money spent, and debt that funds a budget isn't extra investment.

## valuations.csv: publisher estimates (53 rows) · 9 fields
valuation_id · team · publisher · published_date · amount_usd_m · currency · value_type ("unspecified (publisher estimate)") · source_url · note. These are CNBC and Sportico proprietary estimates, credited to them; they are not transaction prices or FCB data.

## sources.csv: source index (78 rows) · 7 fields
source_id · url · issuer · source_type · used_in · access_status (paywalled sources are flagged) · archive_url (empty: archive.org snapshots not yet captured).
