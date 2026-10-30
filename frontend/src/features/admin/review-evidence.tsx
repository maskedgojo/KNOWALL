'use client';

import {useEffect} from 'react';
import {residentApi,str} from '@/lib/endpoints';
import {errorText,useLoad} from '@/lib/use-load';
import {latestOcr,ocrSummary} from '@/lib/ocr-view';
import {OcrFindings,PrivatePreview} from '@/features/documents/documents';
import {Alert,Badge,Button,Card,Loading} from '@/components/ui';
import {Icon} from '@/components/icons';
import {pretty} from '@/lib/format';
import {type SponsorContext,namesComparable} from '@/lib/family-review';

export type OcrReviewState = { loaded:boolean; mismatches:number; warnings:number };

/**
 * The admin application-detail endpoint does not guarantee embedded OCR results.
 * Always fetch the persisted OCR history through the authenticated Flask GET route.
 * This is a read-only request: it NEVER launches another Surya inference run.
 */
export function AdminEvidence({
  document,
  onOpened,
  onOcrState,
  sponsor,
  isFamily,
}: {
  document:Record<string,unknown>;
  onOpened:(documentId:string)=>void;
  onOcrState:(documentId:string,state:OcrReviewState)=>void;
  sponsor:SponsorContext|null;
  isFamily:boolean;
}) {
  const id=str(document.id);
  const name=str(document.original_filename)||str(document.filename)||pretty(str(document.document_type))||'Residence evidence';
  const history=useLoad(()=>residentApi.ocrHistory(id),[id]);
  const finding=latestOcr(history.value);
  const counts=finding?ocrSummary(finding):{matched:0,mismatched:0,unconfirmed:0};
  const applicantNameComparison=finding?.comparisons.find(row=>row.field==='resident_name');
  const extractedName=applicantNameComparison?.extracted??'';
  const matchesSponsor=Boolean(sponsor&&applicantNameComparison&&namesComparable(extractedName,sponsor.display_name));

  useEffect(()=>{
    onOcrState(id,{
      loaded:!history.loading&&!history.error,
      mismatches:counts.mismatched,
      warnings:finding?.warnings.length??0,
    });
  // Report only when fetch result changes; the parsed view is not a stateful dependency.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[id,history.loading,history.error,history.value,onOcrState]);

  return <div className="admin-review-evidence" aria-label={`Review evidence: ${name}`}>
    <Card className="admin-review-original">
      <div className="card-head">
        <div><h2 className="card-title"><Icon name="file" size={17}/>Original uploaded evidence</h2><p className="small muted mt-2">{name}</p></div>
        {typeof document.status==='string'&&<Badge value={document.status}/>}
      </div>
      <PrivatePreview id={id} filename={name} onOpened={()=>onOpened(id)}/>
      <p className="small muted mt-3">Open the original document and manually inspect the identity, residence details, issue date and credibility. OCR alone cannot establish authenticity.</p>
    </Card>
    <Card className="admin-review-ocr">
      <div className="card-head">
        <div><h2 className="card-title"><Icon name="scan" size={17}/>OCR verification details</h2><p className="small muted mt-2">Retrieved from saved Flask OCR history</p></div>
        <Button variant="secondary" disabled={history.loading} onClick={history.refresh}><Icon name="refresh" size={15}/>Refresh</Button>
      </div>
      {history.loading?<Loading label="Loading saved OCR comparisons…"/>:
        history.error?<Alert tone="danger">Could not load the OCR results: {errorText(new Error(history.error))}. Check your session or retry. Do not assume there are no mismatches.</Alert>:
        finding?<>
          {counts.mismatched>0&&<div className="mb-3"><Alert tone="warning">{counts.mismatched} field{counts.mismatched===1?'':'s'} differ from the application. Review each discrepancy before making a decision.</Alert></div>}
          <OcrFindings data={history.value} title="Entered vs extracted information"/>
          {isFamily&&applicantNameComparison&&<div className="mt-3"><Alert tone={matchesSponsor?'info':'warning'}>
            {matchesSponsor
              ?`The extracted resident name also matches the linked sponsor (${sponsor?.display_name}). This is a sponsor-name comparison only; it does not prove the applicant’s identity, family relationship or document authenticity.`
              :sponsor
                ?`The extracted name does not exactly match the linked sponsor (${sponsor.display_name}). The OCR applicant-name difference remains unresolved; review the document and relationship manually.`
                :'For family evidence, an applicant-name mismatch may be expected if the document identifies the sponsor. The verified sponsor name is not supplied by Flask, so this document cannot yet be compared against the sponsor.'}
          </Alert></div>}
        </>:<Alert tone="info">There is no saved OCR run for this document. Inspect the original manually; no comparison or verification is being assumed.</Alert>}
    </Card>
  </div>;
}
