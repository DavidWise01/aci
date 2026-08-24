import '../containment/gate.js';
const {ContainmentGate,ContainmentError,Phase}=globalThis.ACIContainment;
let pass=0,fail=0;
async function t(name,fn){try{await fn();console.log('PASS',name);pass++;}catch(e){console.error('FAIL',name,e);fail++;}}
async function establish(system){const g=ContainmentGate.forSystem(system);const n=g.profile.minBoundaryNodes;await g.defineContainment(Array.from({length:n},(_,i)=>'b'+i));await g.witness('w0',true);await g.witness('w1',true);await g.witness('w2',false);return g;}
await t('plasma blocked before containment',async()=>{const g=ContainmentGate.forSystem('CUBIS');let ok=false;try{await g.armPlasma();}catch(e){ok=e instanceof ContainmentError;}if(!ok)throw new Error('not blocked');});
await t('3 witnesses / 2 approvals verifies',async()=>{const g=ContainmentGate.forSystem('CUBIS');await g.defineContainment(['top','bottom','left','right','front','back']);await g.witness('anchor',true);await g.witness('witness',true);if(g.phase!==Phase.CONTAINMENT_DEFINED)throw new Error('verified early');await g.witness('coherence',false);if(g.phase!==Phase.CONTAINMENT_VERIFIED)throw new Error('not verified');});
await t('CUBIS happy path',async()=>{const g=await establish('CUBIS');await g.armPlasma();await g.ignitePlasma();if(!(await g.guard())||g.phase!==Phase.PLASMA_ACTIVE)throw new Error('inactive');});
await t('runtime tamper quenches',async()=>{const g=await establish('CUBIS');await g.armPlasma();await g.ignitePlasma();g.witnesses.set('w0',false);if(await g.guard())throw new Error('tamper allowed');if(g.phase!==Phase.QUENCHED)throw new Error('not quenched');});
await t('ledger tamper detected',async()=>{const g=await establish('ACI');if(!(await g.verifyLedger()))throw new Error('ledger should pass');g.ledger[0].payload.nodes.push('tamper');if(await g.verifyLedger())throw new Error('tamper missed');});
console.log(`RESULT ${pass}/${pass+fail}`);if(fail)process.exit(1);
