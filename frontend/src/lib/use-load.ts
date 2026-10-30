'use client';
import {useCallback,useEffect,useState} from 'react';
import {ApiError} from './api';
export function errorText(error:unknown){return error instanceof ApiError?error.message:error instanceof Error?error.message:'Unexpected error. Please retry.';}
export function useLoad<T>(factory:()=>Promise<T>,keys:readonly unknown[]=[]){
  const [value,setValue]=useState<T|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [version,setVersion]=useState(0);
  // factory is intentionally supplied as a stable callback where keys change.
  useEffect(()=>{let alive=true;Promise.resolve().then(async()=>{setLoading(true);setError('');try{const result=await factory();if(alive)setValue(result)}catch(e){if(alive)setError(errorText(e))}finally{if(alive)setLoading(false)}});return()=>{alive=false};},[version,...keys]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh=useCallback(()=>setVersion(i=>i+1),[]);
  return {value,loading,error,refresh,setValue};
}
