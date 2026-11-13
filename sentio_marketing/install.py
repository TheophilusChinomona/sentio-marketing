import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_role():
    if not frappe.db.exists("Role", "Sentio Marketing Manager"):
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": "Sentio Marketing Manager",
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)


def setup():
    ensure_role()
    create_custom_fields(
        {
            "CRM Organization": [
                {
                    "fieldname": "sentio_account_id",
                    "label": "Research account ID",
                    "fieldtype": "Data",
                    "unique": 1,
                    "read_only": 1,
                }
            ],
            "CRM Lead": [
                {
                    "fieldname": "sentio_prospect",
                    "label": "Researched prospect",
                    "fieldtype": "Link",
                    "options": "Sentio Prospect",
                    "read_only": 1,
                }
            ],
            "CRM Deal": [
                {
                    "fieldname": "sentio_prospect",
                    "label": "Researched prospect",
                    "fieldtype": "Link",
                    "options": "Sentio Prospect",
                    "read_only": 1,
                }
            ],
        },
        update=True,
    )
    # Manager receives only the CRM entity permissions needed for reviewed imports/promotion.
    for dt in ["CRM Organization", "CRM Lead"]:
        if not frappe.db.exists(
            "Custom DocPerm", {"parent": dt, "role": "Sentio Marketing Manager"}
        ):
            frappe.get_doc(
                {
                    "doctype": "Custom DocPerm",
                    "parent": dt,
                    "parenttype": "DocType",
                    "parentfield": "permissions",
                    "role": "Sentio Marketing Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "permlevel": 0,
                }
            ).insert(ignore_permissions=True)
    frappe.clear_cache()


def configure_site(client_id):
    """CLI-only bootstrap. Does not grant outreach permission or connect a mailbox."""
    settings = frappe.get_single("Sentio Marketing Settings")
    settings.client_id = client_id
    settings.outreach_enabled = 0
    settings.save()
