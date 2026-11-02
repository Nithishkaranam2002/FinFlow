# FinFlow user guide

A short guide for the people who use FinFlow every day. The same content is on the **Help**
page in the app (left sidebar).

## Approval limits at a glance

Limits are set for each company. These are the limits of the demo company, Acme Corp.

| Invoice total | Who can approve |
|---------------|-----------------|
| Under $1,000 | Approved automatically by a business rule, if there are no high-risk flags and the numbers add up |
| $1,000 to $4,999.99 | AP clerk or higher |
| $5,000 to $24,999.99 | Approver or higher |
| $25,000 and above | Controller or higher |
| Any invoice with a high-risk fraud flag | Controller or higher |

## AP Clerk

### Upload an invoice

1. Go to **Invoices** and click **Upload Invoice**.
2. Choose the vendor from the list.
3. Drop the invoice file in the box, or click to browse. PDF, PNG, JPG, WEBP and TIFF work, up to 10 MB.
4. The invoice appears in the list. FinFlow reads it in the background; this usually takes under a minute.

### What each status means

| Status | What it means | What you do |
|--------|---------------|-------------|
| Received | The file is uploaded and waiting to be read. | Nothing, wait a moment. |
| Reading invoice | The AI is reading the invoice. | Nothing, wait a moment. |
| Review Required | Something needs a person to check it. | Open it and follow the steps below. |
| Matched | The invoice was read and is waiting for the next step. | If it stays here, tell your AP lead. |
| Pending Approval | Waiting for the person who has to approve it. | Nothing; the approver takes it from here. |
| Approved | Approved and ready for payment. | Nothing. |
| Rejected | Someone rejected it; the reason is in the Audit Trail. | Follow up with the vendor if needed. |
| Paid | The payment has been made. | Nothing. |

### Review Required and the "Why this needs attention" box

1. Open the invoice. The yellow **Why this needs attention** box at the top lists every reason in plain English, for example
   "AI was not sure about: due date" or "Totals don't add up".
2. Compare the values on screen with the original invoice.
3. Fix wrong values with the pencil icon next to the field, then click **Save**. In Review Required you can always fix the
   invoice number, the total and each line amount. Other fields can be fixed when the AI marked them as unsure.
4. Every change is saved in the **Audit Trail** with your name and the old and new value.
5. When the details are right, let your approver know. They approve it straight from Review Required.

If the box is green and says **All checks passed**, nothing needs your attention.

## Approver

### Approve or reject

1. Open the invoice from **Invoices** (filter by **Pending Approval** or **Review Required**).
2. Read the **Why this needs attention** box and the **Fraud Flags** section.
3. In the **Approval** box:
   - Click **Approve**. Notes are optional.
   - Or type a **rejection reason** (required) and click **Reject**.
4. Your decision is recorded in the Audit Trail.

### Why some invoices need the controller

If the Approval box says **"Requires controller role or higher to approve"**, you cannot approve this invoice. That
happens when:

- the total is $25,000 or more, or
- a fraud check raised a high-risk flag, for example **Just under approval limit** (an amount set just below an approval
  limit, a common way to avoid senior approval) or **Possible duplicate**.

The controller handles these invoices.

## Controller

### Big and flagged invoices

- You approve invoices of $25,000 and more, and any invoice with a high-risk fraud flag.
- Read the **Fraud Flags** section before you decide. Each flag explains what was found, for example
  "Amount $4910.76 is within 5% below the manager approval threshold of $5000.00".
- On the **Reconciliation** page you can also resolve unmatched bank lines with **Manual Match** in the Exception Queue.

### The Integrations page

**Integrations** (left sidebar, controller role and above) shows the connection that sends approved invoices to the ERP system.

- **Green, "Healthy":** the last invoice was delivered.
- **Red, "Last delivery failed":** the last invoice could not be delivered. The red message says why in plain English.
- **Failures (last 24h)** counts deliveries from the last day that are still failed.
- The **Deliveries** table lists every delivery with its status, attempts and last error.

### When it turns red

1. Don't worry about the approval: the invoice is still approved. A failed delivery never undoes or blocks an approval.
2. FinFlow retries automatically after 10 seconds, 30 seconds and 90 seconds.
3. If it is still red, check with the automation team that the receiving system is running.
4. Then click **Retry now** on the failed row. It turns **Sent** and the card goes green.
5. If Retry now fails again, contact the automation team. Retrying is safe: every attempt carries the same key, so the receiving system can spot duplicates.

## What the AI does and does not do

**It does:**

- Read each invoice (vendor, number, dates, amounts, line items) and say how sure it is about each field.
- Help match bank lines to payments when simple rules cannot.

**FinFlow's checks also:**

- Flag problems: totals that don't add up, possible duplicates, amounts just under an approval limit, unusual amounts
  and many invoices from one vendor in a short time. These checks are fixed rules, not AI guesses.

**It does not:**

- Make approval decisions. People approve and reject.
- The only automatic approval is a simple business rule: invoices **under $1,000** with **no high-risk flags** and
  numbers that add up.
- When the AI is not sure about an invoice, it always goes to a person.

## When something looks wrong

- **A field was read wrong and the invoice is in Review Required:** fix it with the pencil icon. The change is logged.
- **A field was read wrong and you cannot edit it** (or the field is missing): do not approve. Reject it with a clear
  reason, or ask your AP lead.
- **Anything else looks wrong** (wrong vendor, a status that does not move, a red Integrations page that does not
  recover): contact your **AP lead** or the **automation team**. Include:
  - the invoice number,
  - which field or page is wrong,
  - the correct value, and
  - a screenshot if you can.

Questions? Ask your AP lead or the automation team.
