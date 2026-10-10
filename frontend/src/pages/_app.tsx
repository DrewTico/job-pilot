import type { AppProps } from 'next/app';
import '../styles/fonts.css';
import '../styles/globals.css';
import '../styles/phone.css';
export default function App({ Component, pageProps }: AppProps) { return <Component {...pageProps} />; }
