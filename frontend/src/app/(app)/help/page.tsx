import { AppTopbar } from "@/components/app-topbar"

export default function HelpPage() {
  return (
    <>
      <AppTopbar title="Help" />
      <div className="mx-auto w-full max-w-2xl flex-1 space-y-4 p-6">
        <h2 className="text-xl font-semibold">Using AetherQore</h2>
        <ol className="list-decimal space-y-3 pl-5 text-sm leading-relaxed text-muted-foreground">
          <li>Sign in with your staff account. Cashiers land on POS; owners land on the command center.</li>
          <li>Sell from Point of Sale. Search or scan a barcode. Totals are calculated by the server. The cart survives a refresh.</li>
          <li>Receive stock by uploading a CSV invoice (see backend/fixtures/sample-invoice.csv) or by approving a purchase order.</li>
          <li>Inventory quantities only change through sales, returns, receiving, or an explicit stock adjustment — every change is in the stock ledger.</li>
          <li>Ask the Copilot about expiry, reorders, or today&apos;s revenue. It reads this computer&apos;s database. Cloud AI is optional and is not required for selling or stock.</li>
          <li>This pharmacy PC is meant to run without internet. Keep using CSV receiving if invoice photos cannot be read offline.</li>
          <li>Daily database backups are stored under the AetherQore data folder. A technician can restore them; see docs/WINDOWS_INSTALL.md.</li>
        </ol>
      </div>
    </>
  )
}
