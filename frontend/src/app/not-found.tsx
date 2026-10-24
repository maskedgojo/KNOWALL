import Link from 'next/link';
export default function NotFound(){return <main className="center-screen"><div className="card text-center"><span className="eyebrow">404 · Page not found</span><h1 className="my-4">We could not find that page</h1><Link className="btn btn-primary" href="/dashboard">Back to your dashboard</Link></div></main>}
