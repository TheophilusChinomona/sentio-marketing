app_name = "sentio_marketing"
app_title = "Sentio Marketing"
app_publisher = "Sentio Langley"
app_description = "Source-backed research and reviewed client outreach"
app_email = ""
app_license = "AGPL-3.0"
required_apps = ["crm"]
before_install = "sentio_marketing.install.ensure_role"
after_install = "sentio_marketing.install.setup"
after_migrate = "sentio_marketing.install.setup"
doc_events = {
    "Sentio Prospect": {"validate": "sentio_marketing.events.validate_prospect"},
    "Sentio Marketing Settings": {
        "validate": "sentio_marketing.events.validate_settings"
    },
    "Sentio Evidence": {"validate": "sentio_marketing.events.validate_evidence"},
    "Sentio Email Draft": {"validate": "sentio_marketing.events.validate_draft"},
    "Sentio Suppression": {"validate": "sentio_marketing.events.validate_suppression"},
    "Communication": {
        "before_insert": "sentio_marketing.events.guard_communication",
        "after_insert": "sentio_marketing.events.record_reply",
    },
    "Email Queue": {"validate": "sentio_marketing.events.guard_queue"},
}

extend_doctype_class = {"Email Queue": ["sentio_marketing.outbound.ReviewedQueueMixin"]}
