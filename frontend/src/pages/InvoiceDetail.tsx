import { useParams } from 'react-router-dom'
import { InvoiceDetailPanel } from '../components/invoices/InvoiceDetail'

export function InvoiceDetailPage() {
  const { invoiceId = '' } = useParams()

  if (!invoiceId) {
    return <p className="text-sm text-danger">Missing invoice ID.</p>
  }

  return <InvoiceDetailPanel invoiceId={invoiceId} />
}
