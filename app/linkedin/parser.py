"""Map raw Voyager payloads onto our clean `Profile` schema.

Split deliberately from the client so it can be unit-tested against saved fixtures with
no network and no cookie. Every section is parsed defensively and independently: a change
in one section's shape degrades that section to an error status instead of failing the
whole profile.

NOTE: the GraphQL-card field paths are finalised against a live capture
(docs/CAPTURE_RECIPE.md); the REST `profileView` extractor below is the first-pass path
and the image/date helpers are shape-stable and covered by tests.
"""
from __future__ import annotations

from typing import Any

from app.linkedin.decode import VoyagerGraph
from app.schemas import (
    Certification,
    ContactInfo,
    DateParts,
    DateRange,
    Education,
    Experience,
    Image,
    ImageArtifact,
    Language,
    Location,
    Profile,
    SectionStatus,
    Skill,
)


# ── shape-stable helpers (unit-tested) ───────────────────────────────────────
def image_from_vector(vector: dict[str, Any] | None) -> Image | None:
    """Build an Image from LinkedIn's vectorImage {rootUrl, artifacts[]} shape."""
    if not isinstance(vector, dict):
        return None
    root = vector.get("rootUrl")
    artifacts = vector.get("artifacts")
    if not root or not isinstance(artifacts, list):
        return None
    out: list[ImageArtifact] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        seg = art.get("fileIdentifyingUrlPathSegment")
        if not seg:
            continue
        out.append(ImageArtifact(url=f"{root}{seg}", width=art.get("width"), height=art.get("height")))
    if not out:
        return None
    out.sort(key=lambda a: a.width or 0)
    return Image(url=out[-1].url, artifacts=out)


def date_parts(value: dict[str, Any] | None) -> DateParts | None:
    if not isinstance(value, dict):
        return None
    if not any(value.get(k) for k in ("year", "month", "day")):
        return None
    return DateParts(year=value.get("year"), month=value.get("month"), day=value.get("day"))


def date_range(time_period: dict[str, Any] | None) -> DateRange | None:
    if not isinstance(time_period, dict):
        return None
    start = date_parts(time_period.get("startDate"))
    end = date_parts(time_period.get("endDate"))
    if start is None and end is None:
        return None
    return DateRange(start=start, end=end)


def _elements(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    section = raw.get(key)
    if isinstance(section, dict):
        elements = section.get("elements")
        if isinstance(elements, list):
            return [e for e in elements if isinstance(e, dict)]
    return []


# ── REST profileView extractor (first-pass) ──────────────────────────────────
def parse_profile_view(raw: dict[str, Any], public_id: str) -> tuple[Profile, list[SectionStatus]]:
    profile = Profile(public_id=public_id)
    statuses: list[SectionStatus] = []

    def section(name: str, fn) -> None:
        try:
            fn()
            statuses.append(SectionStatus(section=name, ok=True))
        except Exception as exc:  # noqa: BLE001 - defensive: one bad section must not kill the rest
            statuses.append(SectionStatus(section=name, ok=False, error=str(exc)))

    def basics() -> None:
        p = raw.get("profile") or {}
        profile.first_name = p.get("firstName")
        profile.last_name = p.get("lastName")
        names = [n for n in (p.get("firstName"), p.get("lastName")) if n]
        profile.full_name = " ".join(names) or None
        profile.headline = p.get("headline")
        profile.about = p.get("summary")
        profile.industry = p.get("industryName")
        loc_text = p.get("geoLocationName") or p.get("locationName")
        if loc_text or p.get("locationName"):
            profile.location = Location(text=loc_text or p.get("locationName"))

    def experience() -> None:
        items: list[Experience] = []
        for el in _elements(raw, "positionView"):
            company = el.get("companyName")
            loc = el.get("locationName") or (el.get("location") or {}).get("basicLocation", {}).get("city")
            items.append(
                Experience(
                    title=el.get("title"),
                    company=company,
                    company_urn=el.get("companyUrn"),
                    location=loc,
                    description=el.get("description"),
                    date_range=date_range(el.get("timePeriod")),
                )
            )
        profile.experience = items

    def education() -> None:
        items: list[Education] = []
        for el in _elements(raw, "educationView"):
            items.append(
                Education(
                    school=el.get("schoolName"),
                    degree=el.get("degreeName"),
                    field_of_study=el.get("fieldOfStudy"),
                    grade=el.get("grade"),
                    activities=el.get("activities"),
                    description=el.get("description"),
                    date_range=date_range(el.get("timePeriod")),
                )
            )
        profile.education = items

    def skills() -> None:
        profile.skills = [Skill(name=el["name"]) for el in _elements(raw, "skillView") if el.get("name")]

    def languages() -> None:
        profile.languages = [
            Language(name=el["name"], proficiency=el.get("proficiency"))
            for el in _elements(raw, "languageView")
            if el.get("name")
        ]

    def certifications() -> None:
        items: list[Certification] = []
        for el in _elements(raw, "certificationView"):
            items.append(
                Certification(
                    name=el.get("name"),
                    authority=el.get("authority"),
                    license_number=el.get("licenseNumber"),
                    url=el.get("url"),
                    date_range=date_range(el.get("timePeriod")),
                )
            )
        profile.certifications = items

    section("basics", basics)
    section("experience", experience)
    section("education", education)
    section("skills", skills)
    section("languages", languages)
    section("certifications", certifications)
    return profile, statuses


def parse_contact_info(raw: dict[str, Any]) -> ContactInfo:
    ci = ContactInfo()
    if not isinstance(raw, dict):
        return ci
    if raw.get("emailAddress"):
        ci.emails = [raw["emailAddress"]]
    websites = raw.get("websites") or []
    ci.websites = [w.get("url") for w in websites if isinstance(w, dict) and w.get("url")]
    phones = raw.get("phoneNumbers") or []
    ci.phones = [p.get("number") for p in phones if isinstance(p, dict) and p.get("number")]
    twitter = raw.get("twitterHandles") or []
    ci.twitter = [t.get("name") for t in twitter if isinstance(t, dict) and t.get("name")]
    ci.birthday = None
    if isinstance(raw.get("birthDateOn"), dict):
        bd = raw["birthDateOn"]
        parts = [str(bd[k]) for k in ("month", "day") if bd.get(k)]
        ci.birthday = "-".join(parts) or None
    ci.address = raw.get("address")
    return ci


# ── Dash normalized profile parser (the current primary path) ────────────────
def date_range_dash(dr: dict[str, Any] | None) -> DateRange | None:
    """Dash dateRange uses {start:{...}, end:{...}} (vs the legacy startDate/endDate)."""
    if not isinstance(dr, dict):
        return None
    start = date_parts(dr.get("start"))
    end = date_parts(dr.get("end"))
    if start is None and end is None:
        return None
    return DateRange(start=start, end=end)


def _find_vector(obj: Any) -> dict[str, Any] | None:
    """Locate the vectorImage dict inside the various nested image containers Dash uses
    (`logo.vectorImage`, `profilePicture.displayImageReference.vectorImage`, …)."""
    if not isinstance(obj, dict):
        return None
    if "rootUrl" in obj and "artifacts" in obj:
        return obj
    for key in ("vectorImage", "displayImageReference", "image"):
        found = _find_vector(obj.get(key))
        if found:
            return found
    return None


def _image(container: Any) -> Image | None:
    return image_from_vector(_find_vector(container))


def parse_dash_profile(response: dict[str, Any], public_id: str | None = None) -> tuple[Profile, list[SectionStatus]]:
    """Parse the normalized {data, included} envelope from identity/dash/profiles."""
    graph = VoyagerGraph(response)
    profile = Profile(public_id=public_id)
    statuses: list[SectionStatus] = []

    elements = graph.data.get("*elements") or graph.data.get("elements") or []
    root_urn = elements[0] if elements else None
    prof = graph.resolve(root_urn) or graph.first_of_type("identity.profile.Profile")
    if not prof:
        return profile, [SectionStatus(section="basics", ok=False, error="Profile entity not found in response.")]

    def section(name: str, fn) -> None:
        try:
            fn()
            statuses.append(SectionStatus(section=name, ok=True))
        except Exception as exc:  # noqa: BLE001 - one bad section must not kill the rest
            statuses.append(SectionStatus(section=name, ok=False, error=str(exc)))

    def basics() -> None:
        profile.public_id = prof.get("publicIdentifier") or public_id
        profile.profile_urn = prof.get("entityUrn")
        profile.first_name = prof.get("firstName")
        profile.last_name = prof.get("lastName")
        names = [n for n in (prof.get("firstName"), prof.get("lastName")) if n]
        profile.full_name = " ".join(names) or None
        profile.headline = prof.get("headline")
        profile.about = prof.get("summary")
        industry = graph.resolve(prof.get("*industry"))
        profile.industry = industry.get("name") if industry else None
        geo = graph.resolve((prof.get("geoLocation") or {}).get("*geo"))
        loc_text = (geo.get("defaultLocalizedName") if geo else None) or prof.get("locationName")
        country = (prof.get("location") or {}).get("countryCode")
        if loc_text or country:
            profile.location = Location(text=loc_text, country=country)
        profile.profile_picture = _image(prof.get("profilePicture"))
        profile.background_image = _image(prof.get("backgroundPicture"))

    def experience() -> None:
        items: list[Experience] = []
        pg_coll = graph.resolve(prof.get("*profilePositionGroups"))
        for gurn in (pg_coll or {}).get("*elements") or []:
            group = graph.resolve(gurn)
            if not group:
                continue
            company = graph.resolve(group.get("*company"))
            logo = _image(company.get("logo")) if company else None
            company_url = company.get("url") if company else None
            group_range = date_range_dash(group.get("dateRange"))
            pos_coll = graph.resolve(group.get("*profilePositionInPositionGroup"))
            pos_urns = (pos_coll or {}).get("*elements") or []
            if not pos_urns:
                items.append(Experience(
                    company=group.get("companyName"), company_urn=group.get("companyUrn"),
                    company_url=company_url, company_logo=logo, date_range=group_range,
                ))
                continue
            for purn in pos_urns:
                pos = graph.resolve(purn)
                if not pos:
                    continue
                items.append(Experience(
                    title=pos.get("title"),
                    company=pos.get("companyName") or group.get("companyName"),
                    company_urn=pos.get("companyUrn") or group.get("companyUrn"),
                    company_url=company_url,
                    company_logo=logo,
                    employment_type=pos.get("employmentType"),
                    location=pos.get("locationName"),
                    description=pos.get("description"),
                    date_range=date_range_dash(pos.get("dateRange")) or group_range,
                ))
        profile.experience = items

    def education() -> None:
        items: list[Education] = []
        ed_coll = graph.resolve(prof.get("*profileEducations"))
        for eurn in (ed_coll or {}).get("*elements") or []:
            ed = graph.resolve(eurn)
            if not ed:
                continue
            school = graph.resolve(ed.get("*school"))
            items.append(Education(
                school=ed.get("schoolName"),
                school_urn=ed.get("schoolUrn"),
                school_url=school.get("url") if school else None,
                school_logo=_image(school.get("logo")) if school else None,
                degree=ed.get("degreeName"),
                field_of_study=ed.get("fieldOfStudy"),
                grade=ed.get("grade"),
                activities=ed.get("activities"),
                description=ed.get("description"),
                date_range=date_range_dash(ed.get("dateRange")),
            ))
        profile.education = items

    def skills() -> None:
        # Present only when the skills card is merged in; empty in FullProfileWithEntities.
        sk_coll = graph.resolve(prof.get("*profileSkills"))
        out: list[Skill] = []
        for surn in (sk_coll or {}).get("*elements") or []:
            sk = graph.resolve(surn)
            if sk and sk.get("name"):
                out.append(Skill(name=sk["name"]))
        profile.skills = out

    section("basics", basics)
    section("experience", experience)
    section("education", education)
    section("skills", skills)
    return profile, statuses
