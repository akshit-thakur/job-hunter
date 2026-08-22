STATUSES = (
    "saved",
    "applied",
    "hr_screen",
    "tech_round",
    "final_round",
    "offer",
    "rejected",
    "withdrawn",
    "closed",
)

WORK_MODES = ("remote", "hybrid", "onsite", "freelance", "unknown")

SOURCES = (
    "linkedin",
    "company_site",
    "referral",
    "job_board",
    "recruiter",
    "naukri",
    "indeed",
    "company_portal",
    "upwork",
    "network",
    "other",
)

CLOSED_STATUSES = ("offer", "rejected", "withdrawn", "closed")

APPLICATION_EVENT_TYPES = (
    "created",
    "applied",
    "status_changed",
    "follow_up_scheduled",
    "follow_up_sent",
    "reply_received",
    "interview_scheduled",
    "interview_completed",
    "resume_sent",
    "referral_added",
    "offer_received",
    "rejected",
    "withdrawn",
    "note_added",
)

APPLICATION_FIELDS = (
    "id",
    "company",
    "role_title",
    "location",
    "work_mode",
    "source",
    "jd_url",
    "salary_min",
    "salary_max",
    "status",
    "resume_version",
    "applied_date",
    "follow_up_date",
    "notes",
    "created_at",
    "updated_at",
)
