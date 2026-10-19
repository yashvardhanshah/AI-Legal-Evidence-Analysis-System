import { CaseDetail } from "../../workspace/components";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <CaseDetail id={id} />; }
