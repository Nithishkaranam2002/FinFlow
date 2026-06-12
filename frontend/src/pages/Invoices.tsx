import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listInvoices, uploadInvoice } from '../api/invoices'
import { listVendors } from '../api/vendors'
import { InvoiceTable } from '../components/invoices/InvoiceTable'
import { UploadDropzone } from '../components/invoices/UploadDropzone'
import type { InvoiceStatus } from '../types'

const PAGE_SIZE = 15

export function InvoicesPage() {
  const queryClient = useQueryClient()
  const [showUpload, setShowUpload] = useState(false)
  const [vendorId, setVendorId] = useState('')
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | ''>('')
  const [vendorSearch, setVendorSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const vendorsQuery = useQuery({
    queryKey: ['vendors'],
    queryFn: listVendors,
  })

  const invoicesQuery = useQuery({
    queryKey: ['invoices', page, statusFilter, dateFrom, dateTo],
    queryFn: () =>
      listInvoices({
        page,
        page_size: PAGE_SIZE,
        status: statusFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
  })

  const uploadMutation = useMutation({
    mutationFn: ({
      file,
      vendorId: vid,
      onProgress,
    }: {
      file: File
      vendorId: string
      onProgress: (percent: number) => void
    }) => uploadInvoice(file, vid, onProgress),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['invoices'] })
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Invoice Pipeline</h2>
          <p className="text-sm text-muted">
            Track extraction, approval, and payment status across your AP workflow.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowUpload((value) => !value)}
          className="rounded-lg bg-primary-900 px-4 py-2 text-sm font-medium text-white hover:bg-primary-800"
        >
          {showUpload ? 'Hide Upload' : 'Upload Invoice'}
        </button>
      </div>

      {showUpload ? (
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <label className="mb-3 block text-sm font-medium text-slate-700">
            Vendor
          </label>
          {vendorsQuery.data?.length ? (
            <select
              value={vendorId}
              onChange={(e) => setVendorId(e.target.value)}
              className="mb-4 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
            >
              <option value="">Select a vendor...</option>
              {vendorsQuery.data.map((vendor) => (
                <option key={vendor.id} value={vendor.id}>
                  {vendor.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={vendorId}
              onChange={(e) => setVendorId(e.target.value)}
              placeholder="Paste vendor UUID"
              className="mb-4 w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
            />
          )}
          <UploadDropzone
            disabled={!vendorId}
            onUpload={async (file, onProgress) => {
              if (!vendorId) throw new Error('Vendor is required')
              return uploadMutation.mutateAsync({ file, vendorId, onProgress })
            }}
          />
        </div>
      ) : null}

      <InvoiceTable
        invoices={invoicesQuery.data?.items ?? []}
        vendors={vendorsQuery.data ?? []}
        total={invoicesQuery.data?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        loading={invoicesQuery.isLoading}
        statusFilter={statusFilter}
        vendorSearch={vendorSearch}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onStatusFilterChange={(value) => {
          setStatusFilter(value)
          setPage(1)
        }}
        onVendorSearchChange={setVendorSearch}
        onDateFromChange={(value) => {
          setDateFrom(value)
          setPage(1)
        }}
        onDateToChange={(value) => {
          setDateTo(value)
          setPage(1)
        }}
        onPageChange={setPage}
        onRefresh={() => {
          void queryClient.invalidateQueries({ queryKey: ['invoices'] })
        }}
      />

      {invoicesQuery.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
          Failed to load invoices.
        </div>
      ) : null}
    </div>
  )
}
