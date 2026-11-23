/**
 * Root.tsx — dibuat baru pada Tahap 2.
 * CATATAN: ~/video-project/src/Root.tsx yang disebut di penugasan TIDAK
 * ditemukan di mesin ini (tidak ada src/ di ~/video-project, tidak ada
 * komposisi lama di mana pun); jadi tidak ada komposisi lama yang dirusak.
 * Komposisi StoryLastSignal didaftarkan di sini, di src/ story-last-signal.
 */
import React from 'react';
import { Composition } from 'remotion';
import StoryLastSignal from './StoryLastSignal';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="StoryLastSignal"
        component={StoryLastSignal}
        durationInFrames={600}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ includeBaseVideo: true }}
      />
    </>
  );
};
