import React from 'react';
import { View } from 'react-native';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { space } from '../theme';
import { PdfPreview, RedlinesRfisWorkspace } from '../redlines/Workspace';

export { PdfPreview, ProofStrip } from '../redlines/Workspace';

export function Redlines({ siteId }: { siteId: string }) {
  const red = useApi<R[]>(`/redlines?site_id=${siteId}`);
  const pdf = red.data?.find((x) => x.PDF_URL)?.PDF_URL;
  return (
    <View style={{ gap: space(4) }}>
      <RedlinesRfisWorkspace siteId={siteId} />
      {pdf ? <PdfPreview path={pdf} startOpen={false} /> : null}
    </View>
  );
}
