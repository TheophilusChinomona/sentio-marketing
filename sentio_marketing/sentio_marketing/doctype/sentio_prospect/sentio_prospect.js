frappe.ui.form.on('Sentio Prospect', {
  refresh(frm) {
    if (frm.is_new()) return
    frm.add_custom_button(__('View evidence'), () => frappe.set_route('List','Sentio Evidence',{prospect:frm.doc.name}))
    const manager = ['System Manager','Sentio Marketing Manager'].some(r => frappe.user_roles.includes(r))
    if (!manager) return
    for (const [label, approve] of [[__('Approve outreach'), true],[__('Reject outreach'), false]]) {
      frm.add_custom_button(label, () => frappe.prompt([{fieldname:'evidence',fieldtype:'Small Text',label:__('Actual recipient-eligibility evidence'),reqd:1}], values => {
        frappe.call({method:'sentio_marketing.api.review_prospect',args:{name:frm.doc.name,evidence:values.evidence,approve},callback:()=>frm.reload_doc()})
      },__('Record review')))
    }
    if (!frm.doc.crm_lead) frm.add_custom_button(__('Create CRM lead'), () => frappe.call({method:'sentio_marketing.api.promote_to_lead',args:{name:frm.doc.name},callback:r=>frappe.set_route('Form','CRM Lead',r.message.name)}))
  }
})
