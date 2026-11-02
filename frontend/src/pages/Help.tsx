import { BadgeCheck, Bot, FileUp, LifeBuoy, ShieldCheck, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'

// Same content as docs/USER_GUIDE.md; keep the two in sync.

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="ff-card p-6">
      <div className="flex items-center gap-2">
        {icon}
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      </div>
      <div className="mt-4 space-y-4 text-sm text-slate-700">{children}</div>
    </section>
  )
}

function SubHeading({ children }: { children: ReactNode }) {
  return <h4 className="text-sm font-semibold text-slate-900">{children}</h4>
}

function Steps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="list-decimal space-y-1.5 pl-5">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ol>
  )
}

function Bullets({ items }: { items: ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead className="bg-canvas text-xs uppercase tracking-wide text-muted">
          <tr>
            {head.map((cell) => (
              <th key={cell} className="px-4 py-2 font-medium">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-t border-border align-top">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className={`px-4 py-2 ${cellIndex === 0 ? 'font-medium text-slate-900' : ''}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const b = (text: string) => <strong className="font-semibold text-slate-900">{text}</strong>

export function HelpPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h2 className="ff-page-title">Help</h2>
        <p className="ff-page-subtitle">How to use FinFlow, in a few short steps for each role.</p>
      </div>

      <Section icon={<BadgeCheck className="h-4 w-4 text-primary-600" />} title="Approval limits at a glance">
        <p>Limits are set for each company. These are the limits of the demo company, Acme Corp.</p>
        <Table
          head={['Invoice total', 'Who can approve']}
          rows={[
            ['Under $1,000', 'Approved automatically by a business rule, if there are no high-risk flags and the numbers add up'],
            ['$1,000 to $4,999.99', 'AP clerk or higher'],
            ['$5,000 to $24,999.99', 'Approver or higher'],
            ['$25,000 and above', 'Controller or higher'],
            ['Any invoice with a high-risk fraud flag', 'Controller or higher'],
          ]}
        />
      </Section>

      <Section icon={<FileUp className="h-4 w-4 text-primary-600" />} title="AP Clerk">
        <SubHeading>Upload an invoice</SubHeading>
        <Steps
          items={[
            <>Go to {b('Invoices')} and click {b('Upload Invoice')}.</>,
            'Choose the vendor from the list.',
            'Drop the invoice file in the box, or click to browse. PDF, PNG, JPG, WEBP and TIFF work, up to 10 MB.',
            'The invoice appears in the list. FinFlow reads it in the background; this usually takes under a minute.',
          ]}
        />

        <SubHeading>What each status means</SubHeading>
        <Table
          head={['Status', 'What it means', 'What you do']}
          rows={[
            ['Received', 'The file is uploaded and waiting to be read.', 'Nothing, wait a moment.'],
            ['Reading invoice', 'The AI is reading the invoice.', 'Nothing, wait a moment.'],
            ['Review Required', 'Something needs a person to check it.', 'Open it and follow the steps below.'],
            ['Matched', 'The invoice was read and is waiting for the next step.', 'If it stays here, tell your AP lead.'],
            ['Pending Approval', 'Waiting for the person who has to approve it.', 'Nothing; the approver takes it from here.'],
            ['Approved', 'Approved and ready for payment.', 'Nothing.'],
            ['Rejected', 'Someone rejected it; the reason is in the Audit Trail.', 'Follow up with the vendor if needed.'],
            ['Paid', 'The payment has been made.', 'Nothing.'],
          ]}
        />

        <SubHeading>Review Required and the "Why this needs attention" box</SubHeading>
        <Steps
          items={[
            <>
              Open the invoice. The yellow {b('Why this needs attention')} box at the top lists every reason in plain
              English, for example "AI was not sure about: due date" or "Totals don't add up".
            </>,
            'Compare the values on screen with the original invoice.',
            <>
              Fix wrong values with the pencil icon next to the field, then click {b('Save')}. In Review Required you
              can always fix the invoice number, the total and each line amount. Other fields can be fixed when the AI
              marked them as unsure.
            </>,
            <>
              Every change is saved in the {b('Audit Trail')} with your name and the old and new value.
            </>,
            'When the details are right, let your approver know. They approve it straight from Review Required.',
          ]}
        />
        <p>
          If the box is green and says {b('All checks passed')}, nothing needs your attention.
        </p>
      </Section>

      <Section icon={<BadgeCheck className="h-4 w-4 text-primary-600" />} title="Approver">
        <SubHeading>Approve or reject</SubHeading>
        <Steps
          items={[
            <>
              Open the invoice from {b('Invoices')} (filter by {b('Pending Approval')} or {b('Review Required')}).
            </>,
            <>
              Read the {b('Why this needs attention')} box and the {b('Fraud Flags')} section.
            </>,
            <>
              In the {b('Approval')} box, click {b('Approve')} (notes are optional), or type a {b('rejection reason')}{' '}
              (required) and click {b('Reject')}.
            </>,
            'Your decision is recorded in the Audit Trail.',
          ]}
        />

        <SubHeading>Why some invoices need the controller</SubHeading>
        <p>
          If the Approval box says {b('"Requires controller role or higher to approve"')}, you cannot approve this
          invoice. That happens when:
        </p>
        <Bullets
          items={[
            'the total is $25,000 or more, or',
            <>
              a fraud check raised a high-risk flag, for example {b('Just under approval limit')} (an amount set just
              below an approval limit, a common way to avoid senior approval) or {b('Possible duplicate')}.
            </>,
          ]}
        />
        <p>The controller handles these invoices.</p>
      </Section>

      <Section icon={<ShieldCheck className="h-4 w-4 text-primary-600" />} title="Controller">
        <SubHeading>Big and flagged invoices</SubHeading>
        <Bullets
          items={[
            'You approve invoices of $25,000 and more, and any invoice with a high-risk fraud flag.',
            <>
              Read the {b('Fraud Flags')} section before you decide. Each flag explains what was found, for example
              "Amount $4910.76 is within 5% below the manager approval threshold of $5000.00".
            </>,
            <>
              On the {b('Reconciliation')} page you can also resolve unmatched bank lines with {b('Manual Match')} in
              the Exception Queue.
            </>,
          ]}
        />

        <SubHeading>The Integrations page</SubHeading>
        <p>
          {b('Integrations')} (left sidebar, controller role and above) shows the connection that sends approved
          invoices to the ERP system.
        </p>
        <Bullets
          items={[
            <>{b('Green, "Healthy":')} the last invoice was delivered.</>,
            <>
              {b('Red, "Last delivery failed":')} the last invoice could not be delivered. The red message says why in
              plain English.
            </>,
            <>{b('Failures (last 24h)')} counts deliveries from the last day that are still failed.</>,
            <>The {b('Deliveries')} table lists every delivery with its status, attempts and last error.</>,
          ]}
        />

        <SubHeading>When it turns red</SubHeading>
        <Steps
          items={[
            "Don't worry about the approval: the invoice is still approved. A failed delivery never undoes or blocks an approval.",
            'FinFlow retries automatically after 10 seconds, 30 seconds and 90 seconds.',
            'If it is still red, check with the automation team that the receiving system is running.',
            <>
              Then click {b('Retry now')} on the failed row. It turns {b('Sent')} and the card goes green.
            </>,
            'If Retry now fails again, contact the automation team. Retrying is safe: every attempt carries the same key, so the receiving system can spot duplicates.',
          ]}
        />
      </Section>

      <Section icon={<Bot className="h-4 w-4 text-primary-600" />} title="What the AI does and does not do">
        <SubHeading>It does</SubHeading>
        <Bullets
          items={[
            'Read each invoice (vendor, number, dates, amounts, line items) and say how sure it is about each field.',
            'Help match bank lines to payments when simple rules cannot.',
          ]}
        />
        <SubHeading>FinFlow's checks also</SubHeading>
        <Bullets
          items={[
            "Flag problems: totals that don't add up, possible duplicates, amounts just under an approval limit, unusual amounts and many invoices from one vendor in a short time. These checks are fixed rules, not AI guesses.",
          ]}
        />
        <SubHeading>It does not</SubHeading>
        <Bullets
          items={[
            'Make approval decisions. People approve and reject.',
            <>
              The only automatic approval is a simple business rule: invoices {b('under $1,000')} with{' '}
              {b('no high-risk flags')} and numbers that add up.
            </>,
            'When the AI is not sure about an invoice, it always goes to a person.',
          ]}
        />
      </Section>

      <section className="ff-card border-amber-200 bg-amber-50/40 p-6">
        <div className="flex items-center gap-2">
          <TriangleAlert className="h-4 w-4 text-amber-700" />
          <h3 className="text-sm font-semibold text-amber-900">When something looks wrong</h3>
        </div>
        <div className="mt-4 space-y-4 text-sm text-amber-900/90">
          <Bullets
            items={[
              <>
                {b('A field was read wrong and the invoice is in Review Required:')} fix it with the pencil icon. The
                change is logged.
              </>,
              <>
                {b('A field was read wrong and you cannot edit it')} (or the field is missing): do not approve. Reject
                it with a clear reason, or ask your AP lead.
              </>,
              <>
                {b('Anything else looks wrong')} (wrong vendor, a status that does not move, a red Integrations page
                that does not recover): contact your {b('AP lead')} or the {b('automation team')}. Include the invoice
                number, which field or page is wrong, the correct value, and a screenshot if you can.
              </>,
            ]}
          />
        </div>
      </section>

      <div className="flex items-center gap-2 text-xs text-muted">
        <LifeBuoy className="h-3.5 w-3.5" />
        Questions? Ask your AP lead or the automation team.
      </div>
    </div>
  )
}
