"use client";

import { useId } from "react";
import styles from "./home-feature-story.module.css";

export function TextLines({ highlighted = false }: { highlighted?: boolean }) {
  return <div className={styles.lines} data-highlighted={highlighted || undefined}>
    <i /><i /><i /><i /><i />
  </div>;
}

export function GrainField() {
  const id = useId().replace(/:/g, "");
  return <div className={styles.grain} aria-hidden="true"><svg viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><pattern id={id} width="19" height="17" patternUnits="userSpaceOnUse" patternTransform="rotate(12)">
      <circle cx="2" cy="3" r="1.4" /><circle cx="12" cy="6" r=".9" /><circle cx="7" cy="13" r="1.1" /><circle cx="17" cy="15" r=".65" />
    </pattern></defs>
    <g fill={`url(#${id})`}>
      <path d="M-160 70C120-180 310-80 440 110S640 420 910 260 1210 230 1380 500L1300 740C1000 380 940 520 710 540S380 530 250 290 50 120-120 350Z" />
      <path opacity=".45" d="M-110 460C110 200 210 460 420 460S690 40 940 10 1160 110 1330-70L1330 160C1110 420 1000 140 840 230S650 690 380 640 160 370-110 690Z" />
    </g>
  </svg></div>;
}
