from .velocity import velocity, estimation
from .moments import MomData, Estimation
import warnings
import numpy as np
from scipy.sparse import issparse, csr_matrix


# incorporate the model selection code soon
def dynamics(adata, filter_gene_mode='final', mode='steady_state', time_key='Time', protein_names=None, experiment_type='deg', assumption_mRNA=None, assumption_protein='ss', concat_data=False):
    """Inclusive model of expression dynamics with scSLAM-seq and multiomics.

    Parameters
    ----------
        adata: :class:`~anndata.AnnData`
            AnnData object
        filter_gene_mode: `str` (default: `final`)
            The string for indicating which mode (one of, ['final', 'basic', 'no']) of gene filter will be used.
        mode: `str` (default: steady_state)
            string indicates which estimation mode will be used. Currently "steady_state" and "moment" methods are supported.
            A "model_selection" mode will be supported soon in which alpha, beta and gamma will be modeled as a function of time.
        time_key: `str` (default: Time)
            The column key for the time label of cells in .obs. Used for either "steady_state" or non-"steady_state" mode or `moment` mode  with labeled data.
        protein_names: `List`
            A list of gene names corresponds to the rows of the measured proteins in the X_protein of the obsm attribute. The names have to be included
            in the adata.var.index.
        experiment_type: str
            labelling experiment type. Available options are:
            (1) 'deg': degradation experiment;
            (2) 'kin': synthesis experiment;
            (3) 'one-shot': one-shot kinetic experiment.
        assumption_mRNA: str
            Parameter estimation assumption for mRNA. Available options are:
            (1) 'ss': pseudo steady state;
            (2) None: kinetic data with no assumption.
            If no labelling data exists, assumption_mRNA will automatically set to be 'ss'.
        assumption_protein: str
            Parameter estimation assumption for protein. Available options are:
            (1) 'ss': pseudo steady state;
        concat_data: bool (default: False)
            Whether to concatenate data before estimation. If your data is a list of matrices for each time point, this need to be set as True.

    Returns
    -------
        adata: :class:`~anndata.AnnData`
            A updated AnnData object with estimated kinetic parameters and inferred velocity included.
    """

    U, Ul, S, Sl, P = None, None, None, None, None # U: unlabeled unspliced; S: unlabel spliced: S
    if filter_gene_mode is 'final':
        valid_ind = adata.var.use_for_dynamo
        # import warnings
        # from scipy.sparse import SparseEfficiencyWarning
        # warnings.simplefilter('ignore', SparseEfficiencyWarning)
    elif filter_gene_mode is 'basic':
        valid_ind = adata.var.pass_basic_filter
    elif filter_gene_mode is 'no':
        valid_ind = np.arange(adata.shape[1])

    if 'X_unspliced' in adata.layers.keys():
        U = adata[:, valid_ind].layers['X_unspliced'].T
    elif 'unspliced' in adata.layers.keys():
        U = adata[:, valid_ind].layers['unspliced'].T

    elif 'X_new' in adata.layers.keys(): # run new / total ratio (NTR)
        U = adata[:, valid_ind].layers['X_new'].T
    elif 'new' in adata.layers.keys():
        U = adata[:, valid_ind].layers['new'].T

    elif 'X_uu' in adata.layers.keys():  # only uu, ul, su, sl provided
        U = adata[:, valid_ind].layers['X_uu'].T # unlabel unspliced: U
    elif 'uu' in adata[:, valid_ind].layers.keys():
        U = adata[:, valid_ind].layers['uu'].T

    if 'X_spliced' in adata.layers.keys():
        S = adata[:, valid_ind].layers['X_spliced'].T
    elif 'spliced' in adata.layers.keys():
        S = adata[:, valid_ind].layers['spliced'].T

    elif 'X_total' in adata.layers.keys(): # run new / total ratio (NTR)
        S = adata[:, valid_ind].layers['X_total'].T
    elif 'total' in adata.layers.keys():
        S = adata[:, valid_ind].layers['total'].T

    elif 'X_su' in adata.layers.keys(): # unlabel spliced: S
        S = adata[:, valid_ind].layers['X_su'].T
    elif 'su' in adata.layers.keys():
        S = adata[:, valid_ind].layers['su'].T

    if 'X_ul' in adata.layers.keys():
        Ul = adata[:, valid_ind].layers['X_ul'].T
    elif 'ul' in adata.layers.keys():
        Ul = adata[:, valid_ind].layers['ul'].T

    if 'X_sl' in adata.layers.keys():
        Sl = adata[:, valid_ind].layers['X_sl'].T
    elif 'sl' in adata.layers.keys():
        Sl = adata[:, valid_ind].layers['sl'].T

    ind_for_proteins = None
    if 'X_protein' in adata.obsm.keys():
        P = adata.obsm['X_protein'].T
    elif 'protein' in adata.obsm.keys():
        P = adata.obsm['protein'].T
    if P is not None:
        if protein_names is None:
            warnings.warn('protein layer exists but protein_names is not provided. No estimation will be performed for protein data.')
        else:
            protein_names = list(set(adata[:, valid_ind].var.index).intersection(protein_names))
            ind_for_proteins = [np.where(adata[:, valid_ind].var.index == i)[0][0] for i in protein_names]
            adata.var['is_protein_velocity_genes'] = False
            adata.var.loc[ind_for_proteins, 'is_protein_velocity_genes'] = True

    t = adata.obs[time_key] if time_key in adata.obs.columns else None

    if Ul is None or Sl is None:
        assumption_mRNA = 'ss'

    if mode is 'steady_state':
        est = estimation(U=U, Ul=Ul, S=S, Sl=Sl, P=P, t=t, ind_for_proteins=ind_for_proteins, experiment_type=experiment_type, assumption_mRNA=assumption_mRNA, \
                         assumption_protein=assumption_protein, concat_data=concat_data)
        est.fit()

        alpha, beta, gamma, eta, delta = est.parameters.values()
        # do this for a vector?
        vel = velocity(** est.parameters)
        vel_U = vel.vel_u(U)
        vel_S = vel.vel_s(U, S)
        vel_P = vel.vel_p(S, P)

        if type(vel_U) is not float:
            adata.layers['velocity_U'] = csr_matrix((adata.shape))
            adata.layers['velocity_U'][:, np.where(valid_ind)[0]] = vel_U.T.tocsr() # np.where(valid_ind)[0] required for sparse matrix
        if type(vel_S) is not float:
            adata.layers['velocity_S'] = csr_matrix((adata.shape))
            adata.layers['velocity_S'][:, np.where(valid_ind)[0]] = vel_S.T.tocsr()
        if type(vel_P) is not float:
            adata.obsm['velocity_P'] = csr_matrix((adata.obsm['P'].shape[0], len(ind_for_proteins)))
            adata.obsm['velocity_P'] = vel_P.T.tocsr()

        if alpha is not None: # for each cell
            adata.varm['kinetic_parameter_alpha'] = np.nan
            adata[:, valid_ind].varm['kinetic_parameter_alpha'] = alpha

        adata.var['kinetic_parameter_avg_alpha'] = alpha.mean(1) if alpha is not None else None

        adata.var['kinetic_parameter_beta'], adata.var['kinetic_parameter_gamma'] = np.nan, np.nan
        adata.var.loc[valid_ind, 'kinetic_parameter_beta'] = beta
        adata.var.loc[valid_ind, 'kinetic_parameter_gamma'] = gamma

        gamma_intercept, gamma_r2, delta_intercept, delta_r2 = est.aux_param.values()
        gamma_r2[~np.isfinite(gamma_r2)] = 0,
        adata.var.loc[valid_ind, 'kinetic_parameter_gamma_intercept'] = gamma_intercept
        adata.var.loc[valid_ind, 'kinetic_parameter_gamma_r2'] = gamma_r2

        if ind_for_proteins is not None:
            delta_r2[~np.isfinite(delta_r2)] = 0
            adata.var['kinetic_parameter_eta'], adata.var['kinetic_parameter_delta'] = np.nan, np.nan
            adata.var.loc[valid_ind, 'kinetic_parameter_eta'][ind_for_proteins] = eta
            adata.var.loc[valid_ind, 'kinetic_parameter_delta'][ind_for_proteins] = delta
            adata.var.loc[valid_ind, 'kinetic_parameter_delta_intercept'][ind_for_proteins] = delta_intercept
            adata.var.loc[valid_ind, 'kinetic_parameter_delta_r2'][ind_for_proteins] = delta_r2

        # add velocity_offset here
    elif mode is 'moment':
        Moment = MomData(adata, time_key)
        adata.uns['M'], adata.uns['V'] = Moment.M, Moment.V
        Est = Estimation(Moment, time_key)
        params, costs = Est.fit()
        a, b, alpha_a, alpha_i, beta, gamma = params[:, 0], params[:, 1], params[:, 2], params[:, 3], params[:, 4], params[:, 5]

        def fbar(x_a, x_i, a, b):
            return b / (a + b) * x_a + a / (a + b) * x_i
        alpha = fbar(alpha_a, alpha_i, a, b)[:, None] ### dimension need to be matched up

        params = {'alpha': alpha, 'beta': beta, 'gamma': gamma}
        vel = velocity(**params)
        vel_U = vel.vel_u(U)
        vel_S = vel.vel_s(U, S)
        vel_P = vel.vel_p(S, P)

        if type(vel_U) is not float:
            adata.layers['velocity_U'] = csr_matrix((adata.shape))
            adata.layers['velocity_U'][:, np.where(valid_ind)[0]] = vel_U.T.tocsr()
        if type(vel_S) is not float:
            adata.layers['velocity_S'] = csr_matrix((adata.shape))
            adata.layers['velocity_S'][:, np.where(valid_ind)[0]] = vel_S.T.tocsr()
        if type(vel_P) is not float:
            adata.obsm['velocity_P'] = csr_matrix((adata.obsm['P'].shape[0], len(ind_for_proteins)))
            adata.obsm['velocity_P'] = vel_P.T.tocsr()

        adata.var['kinetic_parameter_a'], adata.var['kinetic_parameter_b'], adata.var['kinetic_parameter_alpha_a'], \
        adata.var['kinetic_parameter_alpha_i'], adata.var['kinetic_parameter_beta'], \
        adata.var['kinetic_parameter_gamma'] = np.nan, np.nan, np.nan, np.nan, np.nan, np.nan

        adata.var.loc[valid_ind, 'kinetic_parameter_a'] = a
        adata.var.loc[valid_ind, 'kinetic_parameter_b'] = b
        adata.var.loc[valid_ind, 'kinetic_parameter_alpha_a'] = alpha_a
        adata.var.loc[valid_ind, 'kinetic_parameter_alpha_i'] = alpha_i
        adata.var.loc[valid_ind, 'kinetic_parameter_beta'] = beta
        adata.var.loc[valid_ind, 'kinetic_parameter_gamma'] = gamma
        # add velocity_offset here
    elif mode is 'model_selection':
        warnings.warn('Not implemented yet.')

    return adata
