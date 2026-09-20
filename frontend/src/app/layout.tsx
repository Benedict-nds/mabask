import type { Metadata, Viewport } from 'next'
import { cookies } from 'next/headers'
import { Providers } from '@/app/providers'
import './globals.css'

export const metadata: Metadata = {
  title: 'AetherQore — Pharmacy Operating System',
  description:
    'AetherQore is the pharmacy operating system for inventory, purchasing, point of sale, and reports. It runs on this computer without an internet connection.',
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: '#10B981',
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const scheme = (await cookies()).get('aq.color-scheme')?.value
  const themeClass = scheme === 'dark' ? 'dark' : scheme === 'light' ? 'light' : ''

  return (
    <html lang="en" suppressHydrationWarning className={`bg-background ${themeClass}`.trim()}>
      <body className="font-sans antialiased">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}