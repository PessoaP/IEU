import numpy as np
import pandas as pd
import smn
from basis import *
from scipy.linalg import expm

from models import lam_2S as get_lam

@njit
def arnoldi(A, b, n):
    h = np.zeros((n+1,n))
    Qt = np.zeros((n+1,A.shape))

    q = b/np.linalg.norm(b)
    Qt[0] = q

    for k in range(n):
        v = smn.dot(q,A)
        for j in range(k+1):
            q = Qt[j]
            h[j,k] = np.dot(q,v)
            v = v - h[j,k]*q
        h[k+1,k] = np.linalg.norm(v)

        if h[k+1,k] > 1e-12:
            q = v/h[k+1,k] 
            Qt[k+1] = q
        else:
            Q = Qt.T
            return Q[:k,:k-1],h[:k-1, :k]
    Q=Qt.T
    return Q[:,:-1],h[:-1, :]

@njit
def kryreconstruct(Q,exp_H,rho):
    exp_col = np.ascontiguousarray(exp_H[:,0])
    return np.dot(Q,exp_col)*np.linalg.norm(rho)

def evolve_KRY(rho,A,dt,kappa):
    Q, H = arnoldi(A, rho, kappa)
    exp_H = expm(dt*H)
    return kryreconstruct(Q,exp_H,rho)


def solve(rho_0,A,T,dt,kappa=20):
    rho=1.0*rho_0
    t=0*dt
    while t+dt<T:
        t+=dt
        rho = evolve_KRY(rho,A,dt,kappa)
    return evolve_KRY(rho,A,T-t,kappa)

#@njit
def take_points(pe,w_all,T_ind,N_RNA): #ideally there must be a way to turn the previous and this into a single one
    return pe[T_ind,w_all] + pe[T_ind,w_all+N_RNA]

class params:
    def __init__(self,theta,N_RNA,kappa=20):
        N_DNA = 2
        birth,d,l01,l10 = 1.0*theta
        self.value=theta
        
        rho = make_initial(0,0,N_RNA*N_DNA)##this creates on inactive state
        self.rho = rho
        
        self.N_RNA = N_RNA
        self.N = N_RNA*N_DNA
        self.lam = get_lam(birth,d,l01,l10,N_RNA,N_DNA)
        self.A = smn.get_A(self.lam)
        self.dt = 2.0*kappa/(np.abs(self.A.values).max())
        self.kappa = kappa

        self.log_prior = lprior(theta)
        
        
    def likes(self,T_unique):
        rho = self.rho*1.0
        rho_t = []
        t=0
        for T in T_unique:
            rho = solve(rho,self.A,T-t,self.dt,self.kappa)
            rho_t.append(rho)
            t=T
        return np.vstack(rho_t)

    def loglike_w(self,w_all,T_all):
        T_unique,T_ind = np.unique(T_all,return_inverse=True)
        pe_theta = self.likes(T_unique)
        return np.log(take_points(pe_theta,w_all,T_ind,self.N_RNA))

    
def update_S(th_list):
    return (np.cov(np.log(th_list).T,bias=True) + np.eye(4)*1e-12)*((2.38/np.sqrt(4))**2) 

def update_th(ll,w_all,T_all,th,S_prop):
    value_prop = np.exp(np.random.multivariate_normal(np.log(th.value),S_prop))
    th_prop = params(value_prop,th.N_RNA)
    ll_prop = th_prop.loglike_w(w_all,T_all)

    update = np.log(np.random.rand()) < ll_prop.sum() - ll.sum() + th_prop.log_prior -th.log_prior
    if update:
        return ll_prop,th_prop
    return ll,th

def save(ll_list,th_list,beta_gt):
    ll_pd = np.stack(ll_list)
    th_pd = np.stack(th_list)

    df = pd.DataFrame(th_pd,columns=['birth rate','death rate','activation rate','deactivtion rate'])
    df['log p(w|th)'] = ll_pd

    df.to_csv('inference/2S_KRY_inference_beta={}.csv'.format(beta_gt),index=False)