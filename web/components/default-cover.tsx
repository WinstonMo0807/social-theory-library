import { defaultCoverTitle, defaultCoverVariant } from '@/lib/default-cover';
import styles from './default-cover.module.css';

export function DefaultCover({ title, author, identity, issue, className }: {
  title: string; author?: string; identity?: string; issue?: string; className?: string;
}) {
  const variant = defaultCoverVariant(identity || title);
  return <span className={`${styles.cover}${className ? ` ${className}` : ''}`} data-default-cover={variant} role="img" aria-label={`${title}，自动排版封面`} title={title}>
    <svg className={styles.art} viewBox="0 0 200 300" preserveAspectRatio="none" aria-hidden="true">
      {variant === 0 ? <><circle cx="212" cy="305" r="155" fill="none" stroke="currentColor" strokeWidth=".7"/><circle cx="220" cy="316" r="104" fill="none" stroke="#aa854d" strokeWidth=".8"/></> :
       variant === 1 ? <><path d="M0 198H132V300H0Z" fill="#b8afa0"/><path d="M90 242H200V300H90Z" fill="#343432"/></> :
       variant === 2 ? <><path d="M132 300L200 136V300Z" fill="#686760"/><path d="M0 300L200 238V300Z" fill="#b2a18a"/></> :
       variant === 3 ? <>{[0,1,2,3,4,5,6,7].map(n=><path key={n} d={`M${-16+n*16} 310C${24+n*12} ${224+n*7} ${178+n*8} ${278-n*6} 215 ${142+n*14}`} fill="none" stroke="currentColor" strokeWidth=".45"/>)}</> :
       variant === 4 ? <><path d="M82 301V158H201" fill="none" stroke="currentColor" strokeWidth=".8"/><path d="M154 214H200V300H154Z" fill="#aa854d"/></> :
       <><ellipse cx="163" cy="225" rx="112" ry="66" transform="rotate(-37 163 225)" fill="none" stroke="currentColor" strokeWidth=".65"/><path d="M116 301V205H201" fill="none" stroke="currentColor" strokeWidth=".65"/></>}
    </svg>
    <span className={styles.copy}><strong>{defaultCoverTitle(title)}</strong>{issue ? <small>{issue}</small> : author ? <small>{author}</small> : null}</span>
  </span>;
}
