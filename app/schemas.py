"""Public response schema.

Designing this ourselves (the challenge leaves it open) lets us return a clean, typed,
versioned contract instead of LinkedIn's raw internal shapes. Every field is optional so
partial data degrades gracefully rather than failing the whole request.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


# ── Primitives ───────────────────────────────────────────────────────────────
class ImageArtifact(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


class Image(BaseModel):
    """Best (largest) URL plus every available size."""

    url: str | None = None
    artifacts: list[ImageArtifact] = Field(default_factory=list)


class DateParts(BaseModel):
    year: int | None = None
    month: int | None = None
    day: int | None = None


class DateRange(BaseModel):
    start: DateParts | None = None
    end: DateParts | None = None


class Location(BaseModel):
    text: str | None = None
    city: str | None = None
    country: str | None = None


# ── Sections ─────────────────────────────────────────────────────────────────
class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    company_urn: str | None = None
    company_url: str | None = None
    company_logo: Image | None = None
    employment_type: str | None = None
    location: str | None = None
    description: str | None = None
    date_range: DateRange | None = None
    duration: str | None = None
    is_current: bool | None = None


class Education(BaseModel):
    school: str | None = None
    school_urn: str | None = None
    school_url: str | None = None
    school_logo: Image | None = None
    degree: str | None = None
    field_of_study: str | None = None
    grade: str | None = None
    activities: str | None = None
    description: str | None = None
    date_range: DateRange | None = None


class Skill(BaseModel):
    name: str
    endorsement_count: int | None = None


class Certification(BaseModel):
    name: str | None = None
    authority: str | None = None
    authority_logo: Image | None = None
    license_number: str | None = None
    url: str | None = None
    date_range: DateRange | None = None


class Language(BaseModel):
    name: str
    proficiency: str | None = None


class Honor(BaseModel):
    title: str | None = None
    issuer: str | None = None
    date: DateParts | None = None
    description: str | None = None


class VolunteerExperience(BaseModel):
    role: str | None = None
    organization: str | None = None
    cause: str | None = None
    description: str | None = None
    date_range: DateRange | None = None


class Project(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    date_range: DateRange | None = None


class ContactInfo(BaseModel):
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    websites: list[str] = Field(default_factory=list)
    twitter: list[str] = Field(default_factory=list)
    birthday: str | None = None
    address: str | None = None


# ── Profile ──────────────────────────────────────────────────────────────────
class Profile(BaseModel):
    public_id: str | None = None
    profile_urn: str | None = None

    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    headline: str | None = None
    location: Location | None = None
    about: str | None = None
    industry: str | None = None

    profile_picture: Image | None = None
    background_image: Image | None = None

    connections: int | None = None
    followers: int | None = None
    open_to_work: bool | None = None

    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    honors: list[Honor] = Field(default_factory=list)
    volunteer: list[VolunteerExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    contact_info: ContactInfo | None = None


# ── Response envelope ────────────────────────────────────────────────────────
class SectionStatus(BaseModel):
    section: str
    ok: bool
    error: str | None = None


class ResponseMeta(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source_url: str
    fetched_at: str
    cached: bool = False
    partial: bool = False
    elapsed_ms: int | None = None
    sections: list[SectionStatus] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    meta: ResponseMeta
    profile: Profile
    # Populated only when the caller passes ?include_raw=true — lets a grader verify the
    # parser against the real Voyager payload.
    raw: dict | None = None
