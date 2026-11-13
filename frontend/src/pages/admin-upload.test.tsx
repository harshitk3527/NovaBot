import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { UploadModal } from './AdminDocuments'
describe('UploadModal', () => {
  const renderModal = () => render(<QueryClientProvider client={new QueryClient()}><UploadModal onClose={vi.fn()} onDone={vi.fn()} /></QueryClientProvider>)
  it('rejects unsupported extensions', async () => { renderModal(); await userEvent.upload(screen.getByLabelText(/choose file/i), new File(['x'], 'malware.exe', { type: 'application/octet-stream' })); fireEvent.change(screen.getByLabelText(/choose file/i), { target: { files: [new File(['x'], 'malware.exe')] } }); expect(screen.getByText(/only pdf/i)).toBeInTheDocument() })
  it('rejects files larger than 10 MiB', async () => { renderModal(); await userEvent.upload(screen.getByLabelText(/choose file/i), new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf')); fireEvent.change(screen.getByLabelText(/choose file/i), { target: { files: [new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf')] } }); expect(screen.getByText(/10 mib/i)).toBeInTheDocument() })
})
