import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/webAuth';

export default function LawsTestsAuthorize(){
  const { user, isAuthenticated, isAuthLoading }=useAuth();
  const location=useLocation();
  const [error,setError]=React.useState('');
  const [busy,setBusy]=React.useState(false);
  const state=new URLSearchParams(location.search).get('state')??'';
  const target=import.meta.env.VITE_LAWS_TEST_PUBLIC_URL || 'https://tests.jurisigta.eu';
  if(isAuthLoading)return <p>Načítavam prihlásenie…</p>;
  if(!isAuthenticated)return <Navigate to="/auth" replace state={{from:location}}/>;
  async function proceed(){
    setBusy(true);setError('');
    try{
      if(!user?.deviceAuthToken||!user?.deviceId||state.length<32)throw new Error('Prihláste sa znova a otvorte testy cez prihlasovacie tlačidlo.');
      const response=await fetch(target+'/api/auth/authorize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state,user_id:user.userId,device_id:user.deviceId,device_token:user.deviceAuthToken})});
      const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Prihlásenie sa nepodarilo.');
      const redirect=new URL(data.redirect);if(redirect.origin!==new URL(target).origin||redirect.pathname!=='/api/auth/callback')throw new Error('Neplatný návrat do testov.');
      window.location.replace(redirect.href);
    }catch(e){setError((e as Error).message);setBusy(false)}
  }
  return <section className="page-section"><h1>Pokračovať do JurisDigta testov</h1><p>Použijeme váš existujúci účet. Ukladajú sa iba vaše odpovede, výsledky a spätná väzba. Históriu môžete vymazať.</p>{error&&<p role="alert">{error}</p>}<button className="button primary" disabled={busy} onClick={proceed}>{busy?'Prihlasujem…':'Pokračovať do testov'}</button></section>;
}
