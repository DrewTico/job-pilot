// Development-only exported page. Excluded from the Python delivery manifest.
import { Workspace } from '../components/workspace';
import { fixtureReader } from '../fixtures/reader';
export default function DemoReview() { return <Workspace reader={fixtureReader} synthetic />; }
