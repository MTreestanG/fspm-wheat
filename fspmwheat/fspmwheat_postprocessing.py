# -*- coding: latin-1 -*-

import os
import pandas as pd
import numpy as np
import statsmodels.api as sm

from cnwheat import model as cnwheat_model


def leaf_traits(scenario_outputs_dirpath, scenario_postprocessing_dirpath):
    """
    Average RUE and photosynthetic yield for the whole cycle.

    :param str scenario_outputs_dirpath: the path to the CSV outputs file of the scenario
    :param str scenario_postprocessing_dirpath: the path to the CSV postprocessing file of the scenari
    """

    # --- Import simulations outputs/prostprocessings
    df_axe = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'axes_outputs.csv'))
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_hz = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'hiddenzones_outputs.csv'))

    # --- Extract key values per leaf
    res = df_hz.copy()
    res = res[(res['axis'] == 'MS') & (res['plant'] == 1) & ~np.isnan(res.leaf_Lmax)].copy()
    res_IN = res[~ np.isnan(res.internode_Lmax)]
    last_value_idx = res.groupby(['metamer'])['t'].transform(max) == res['t']
    res = res[last_value_idx].copy()
    res['lamina_Wmax'] = res.leaf_Wmax
    res['lamina_W_Lg'] = res.leaf_Wmax / res.lamina_Lmax
    last_value_idx = res_IN.groupby(['metamer'])['t'].transform(max) == res_IN['t']
    res_IN = res_IN[last_value_idx].copy()
    leaf_traits_df = res[['metamer', 'leaf_Lmax', 'leaf_Lmax_em', 'lamina_Lmax', 'sheath_Lmax', 'lamina_Wmax', 'lamina_W_Lg', 'SSLW', 'LSSW']].merge(res_IN[['metamer', 'internode_Lmax']],
                                                                                                                                                     left_on='metamer',
                                                                                                                                                     right_on='metamer',
                                                                                                                                                     how='outer').copy()
    # Lamina max width / max length at leaf emergence
    res_em = df_hz[(df_hz['axis'] == 'MS') & (df_hz['plant'] == 1) & ~np.isnan(df_hz.leaf_Wmax)].copy()
    em_idx = res_em.groupby(['metamer'])['t'].transform(min) == res_em['t']
    res_em = res_em[em_idx].copy()
    res_em['lamina_W_Lg_em'] = res_em.leaf_Wmax / res_em.lamina_Lmax
    leaf_traits_df = leaf_traits_df.merge(res_em[['metamer', 'lamina_W_Lg_em']], on='metamer', how='outer')

    # --- Simulated RER

    # import simulation outputs
    data_RER = df_hz.copy()
    data_RER = data_RER[(data_RER.axis == 'MS') & (data_RER.metamer >= 4)].copy()
    data_RER.sort_values(['t', 'metamer'], inplace=True)
    data_teq = df_axe.copy()
    data_teq = data_teq[data_teq.axis == 'MS'].copy()

    # Time previous leaf emergence
    tmp = data_RER[data_RER.leaf_is_emerged]
    leaf_em = tmp.groupby('metamer', as_index=False)['t'].min()
    leaf_em['t_em'] = leaf_em.t
    leaf_em = leaf_em.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    leaf_em['sumTT_em'] = leaf_em.sum_TT
    leaf_traits_df = leaf_traits_df.merge(leaf_em[['metamer', 't_em', 'sumTT_em']], on='metamer', how='outer')
    prev_leaf_em = leaf_em.copy()
    prev_leaf_em.metamer = leaf_em.metamer + 1
    prev_leaf_em['sumTT_em_prev'] = prev_leaf_em['sumTT_em']
    phyllo = leaf_em.merge(prev_leaf_em[['metamer', 'sumTT_em_prev']], on='metamer', how='outer')
    phyllo['phyllo_TT'] = phyllo.sumTT_em - phyllo.sumTT_em_prev
    leaf_traits_df = leaf_traits_df.merge(phyllo[['metamer', 'phyllo_TT', 'sumTT_em_prev']], on='metamer', how='outer')

    data_RER2 = pd.merge(data_RER, prev_leaf_em[['metamer', 't_em']], on='metamer')
    data_RER2 = data_RER2[data_RER2.t <= data_RER2.t_em]

    # SumTimeEq
    data_teq['SumTimeEq'] = np.cumsum(data_teq.delta_teq)
    data_RER3 = pd.merge(data_RER2, data_teq[['t', 'SumTimeEq']], on='t')

    # logL
    data_RER3['logL'] = np.log(data_RER3.leaf_L)

    # Estimate RER
    leaf_traits_df['RER'] = np.nan
    for leaf in data_RER3.metamer.drop_duplicates():
        Y = data_RER3.logL[data_RER3.metamer == leaf]
        X = data_RER3.SumTimeEq[data_RER3.metamer == leaf]
        X = sm.add_constant(X)
        mod = sm.OLS(Y, X)
        fit_RER = mod.fit()
        leaf_traits_df.loc[leaf_traits_df.metamer == leaf, 'RER'] = fit_RER.params['SumTimeEq']

    # --- Time of leaf initiation
    leaf_init = df_hz.groupby('metamer', as_index=False)['t'].min()
    leaf_init.loc[leaf_init.t == 0, 't'] = np.nan
    leaf_init['t_init'] = leaf_init.t
    leaf_init = leaf_init.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    leaf_init['sumTT_init'] = leaf_init.sum_TT
    leaf_traits_df = leaf_traits_df.merge(leaf_init[['metamer', 'sumTT_init']], on='metamer', how='outer')
    leaf_traits_df['ageTT_init_em_prev'] = leaf_traits_df.sumTT_em_prev - leaf_traits_df.sumTT_init

    # --- Time ligulation
    df_lam = df_elt[(df_elt.axis == 'MS') & (df_elt.element == 'LeafElement1')].copy()
    df_lam_green = df_lam[(~df_lam.is_growing) & (df_lam.senesced_mstruct == 0)]
    lamina_lig = df_lam_green.groupby('metamer', as_index=False)['t'].min()
    lamina_lig['t_lig'] = lamina_lig.t
    lamina_lig = lamina_lig.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    lamina_lig['sumTT_lig'] = lamina_lig.sum_TT
    leaf_traits_df = leaf_traits_df.merge(lamina_lig[['metamer', 't_lig', 'sumTT_lig']], on='metamer', how='outer')
    leaf_traits_df.loc[leaf_traits_df['metamer'] < 3, 't_lig'] = np.nan
    leaf_traits_df.loc[leaf_traits_df['metamer'] < 3, 'sumTT_lig'] = np.nan
    leaf_traits_df['ageTT_lig'] = leaf_traits_df.sumTT_lig - leaf_traits_df.sumTT_em

    # --- Time onset of senescence
    tmp = df_lam[df_lam.senesced_mstruct > 0]
    tmp2 = tmp.groupby('metamer', as_index=False)['t'].min()
    tmp2['t_senesc_onset'] = tmp2.t
    tmp2 = tmp2.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    tmp2['sumTT_senesc_onset'] = tmp2.sum_TT
    leaf_traits_df = leaf_traits_df.merge(tmp2[['metamer', 't_senesc_onset', 'sumTT_senesc_onset']], on='metamer', how='outer')
    leaf_traits_df['ageTT_senesc_onset'] = leaf_traits_df.sumTT_senesc_onset - leaf_traits_df.sumTT_em

    # --- Time end of senescence
    tmp = df_lam[df_lam.mstruct == 0]
    tmp2 = tmp.groupby('metamer', as_index=False)['t'].min()
    tmp2['t_senesc_end'] = tmp2.t
    tmp2 = tmp2.merge(df_axe[['t', 'sum_TT']], on='t', how='left')
    tmp2['sumTT_senesc_end'] = tmp2.sum_TT
    leaf_traits_df = leaf_traits_df.merge(tmp2[['metamer', 't_senesc_end', 'sumTT_senesc_end']], on='metamer', how='outer')
    leaf_traits_df['ageTT_senesc_end'] = leaf_traits_df.sumTT_senesc_end - leaf_traits_df.sumTT_em

    # --- Lifespan
    leaf_traits_df['lifespanTT_lig_green'] = leaf_traits_df.sumTT_senesc_onset - leaf_traits_df.sumTT_lig
    leaf_traits_df['lifespanTT_lig'] = leaf_traits_df.sumTT_senesc_end - leaf_traits_df.sumTT_lig

    # --- Mean SLA and SLN in between ligulation and onset of senescence
    leaf_traits_df = leaf_traits_df.merge(df_lam_green.groupby('metamer', as_index=False).aggregate({'SLN': 'mean', 'SLA': 'mean'}), on='metamer', how='outer')

    # --- Save results in postprocessing directory
    leaf_traits_df.sort_values('metamer', inplace=True)
    leaf_traits_df.to_csv(os.path.join(scenario_postprocessing_dirpath, 'leaf_traits.csv'), index=False, na_rep='NA')


def table_C_usages(scenario_postprocessing_dirpath):
    """ Calculate C usage from postprocessings and save it to a CSV file

    :param str scenario_postprocessing_dirpath: the path to the CSV file describing all scenarii

    """
    # --- Import simulations prostprocessings
    df_axe = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'axes_postprocessing.csv'))
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_org = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'organs_postprocessing.csv'))
    df_hz = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'hiddenzones_postprocessing.csv'))

    df_roots = df_org[df_org['organ'] == 'roots'].copy()
    df_phloem = df_org[df_org['organ'] == 'phloem'].copy()

    # --- C usages relatif to Net Photosynthesis
    AMINO_ACIDS_C_RATIO = cnwheat_model.EcophysiologicalConstants.AMINO_ACIDS_C_RATIO  #: Mean number of mol of C in 1 mol of the major amino acids of plants (Glu, Gln, Ser, Asp, Ala, Gly)
    AMINO_ACIDS_N_RATIO = cnwheat_model.EcophysiologicalConstants.AMINO_ACIDS_N_RATIO  #: Mean number of mol of N in 1 mol of the major amino acids of plants (Glu, Gln, Ser, Asp, Ala, Gly)

    # Photosynthesis
    df_elt['Photosynthesis_tillers'] = df_elt['Photosynthesis'].fillna(0) * df_elt['nb_replications'].fillna(1.)
    Tillers_Photosynthesis_Ag = df_elt.groupby(['t'], as_index=False).agg({'Photosynthesis_tillers': 'sum'})
    C_usages = pd.DataFrame({'t': Tillers_Photosynthesis_Ag['t']})
    C_usages['C_produced'] = np.cumsum(Tillers_Photosynthesis_Ag.Photosynthesis_tillers)

    # Respiration
    C_usages['Respi_roots'] = np.cumsum(df_axe.C_respired_roots)
    C_usages['Respi_shoot'] = np.cumsum(df_axe.C_respired_shoot)

    # Exudation
    C_usages['exudation'] = np.cumsum(df_axe.C_exudated.fillna(0))

    # Structural growth
    C_consumption_mstruct_roots = df_roots.sucrose_consumption_mstruct.fillna(0) + df_roots.AA_consumption_mstruct.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    C_usages['Structure_roots'] = np.cumsum(C_consumption_mstruct_roots.reset_index(drop=True))

    df_hz['C_consumption_mstruct'] = df_hz.sucrose_consumption_mstruct.fillna(0) + df_hz.AA_consumption_mstruct.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_hz['C_consumption_mstruct_tillers'] = df_hz['C_consumption_mstruct'] * df_hz['nb_replications']
    C_consumption_mstruct_shoot = df_hz.groupby(['t'])['C_consumption_mstruct_tillers'].sum()
    C_usages['Structure_shoot'] = np.cumsum(C_consumption_mstruct_shoot.reset_index(drop=True))

    # Non structural C
    df_phloem['C_NS'] = df_phloem.sucrose.fillna(0) + df_phloem.amino_acids.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    C_NS_phloem_init = df_phloem.C_NS - df_phloem.C_NS.reset_index(drop=True)[0]
    C_usages['NS_phloem'] = C_NS_phloem_init.reset_index(drop=True)

    df_elt['C_NS'] = df_elt.sucrose.fillna(0) + df_elt.fructan.fillna(0) + df_elt.starch.fillna(0) + (
            df_elt.amino_acids.fillna(0) + df_elt.proteins.fillna(0)) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_elt['C_NS_tillers'] = df_elt['C_NS'] * df_elt['nb_replications'].fillna(1.)
    C_elt = df_elt.groupby(['t']).agg({'C_NS_tillers': 'sum'})

    df_hz['C_NS'] = df_hz.sucrose.fillna(0) + df_hz.fructan.fillna(0) + (df_hz.amino_acids.fillna(0) + df_hz.proteins.fillna(0)) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO
    df_hz['C_NS_tillers'] = df_hz['C_NS'] * df_hz['nb_replications'].fillna(1.)
    C_hz = df_hz.groupby(['t']).agg({'C_NS_tillers': 'sum'})

    df_roots['C_NS'] = df_roots.sucrose.fillna(0) + df_roots.amino_acids.fillna(0) * AMINO_ACIDS_C_RATIO / AMINO_ACIDS_N_RATIO

    C_NS_autre = df_roots.C_NS.reset_index(drop=True) + C_elt.C_NS_tillers.reset_index(drop=True) + C_hz.C_NS_tillers.reset_index(drop=True)
    C_NS_autre_init = C_NS_autre - C_NS_autre.reset_index(drop=True)[0]
    C_usages['NS_other'] = C_NS_autre_init.reset_index(drop=True)

    # Total
    C_usages['C_budget'] = (C_usages.Respi_roots + C_usages.Respi_shoot + C_usages.exudation + C_usages.Structure_roots + C_usages.Structure_shoot + C_usages.NS_phloem + C_usages.NS_other) / \
                           C_usages.C_produced

    C_usages.to_csv(os.path.join(scenario_postprocessing_dirpath, 'C_usages.csv'), index=False)


def calculate_performance_indices(scenario_outputs_dirpath, scenario_postprocessing_dirpath, meteo_dirpath, plant_density):
    """
    Average RUE and photosynthetic yield for the whole cycle.

    :param str scenario_postprocessing_dirpath: the path to the CSV file describing all scenarii
    :param str meteo_dirpath: the path to the CSV meteo file
    :param int plant_density: the plant density (plant m-2)
    """

    # --- Import simulations prostprocessings and outputs
    df_elt = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'elements_postprocessing.csv'))
    df_axe = pd.read_csv(os.path.join(scenario_postprocessing_dirpath, 'axes_postprocessing.csv'))
    df_axe_out = pd.read_csv(os.path.join(scenario_outputs_dirpath, 'axes_outputs.csv'))

    # --- Import meteo file for incident PAR
    df_meteo = pd.read_csv(meteo_dirpath)

    # --- RUE (g DM. MJ-1 PARa)
    df_elt['PARa_MJ'] = df_elt['PARa'] * df_elt['green_area'] * df_elt['nb_replications'].fillna(
        1.) * 3600 / 4.6 * 10 ** -6  # Si tallage, il faut alors utiliser les calculcs green_area et PARa des talles.
    df_elt['RGa_MJ'] = df_elt['PARa'] * df_elt['green_area'] * df_elt['nb_replications'].fillna(
        1.) * 3600 / 2.02 * 10 ** -6  # Si tallage, il faut alors utiliser les calculcs green_area et PARa des talles.
    PARa = df_elt.groupby(['t'])['PARa_MJ'].agg('sum')
    PARa_cum = np.cumsum(PARa)

    RUE_shoot = np.polyfit(PARa_cum, df_axe.sum_dry_mass_shoot, 1)[0]
    RUE_plant = np.polyfit(PARa_cum, df_axe.sum_dry_mass, 1)[0]

    # --- RUE (g DM. MJ-1 RGint estimated from LAI using Beer-Lambert's law with extinction coefficient of 0.4)

    # Beer-Lambert
    df_LAI = df_elt[(df_elt.element == 'LeafElement1')].groupby(['t']).agg({'green_area': 'sum'})
    df_LAI['LAI'] = df_LAI.green_area * plant_density
    df_LAI['t'] = df_LAI.index

    toto = df_meteo[['t', 'PARi']].merge(df_LAI[['t', 'LAI']], on='t', how='inner')
    toto['PARint_BL'] = toto.PARi * (1 - np.exp(-0.4 * toto.LAI))
    toto['RGint_BL_MJ'] = toto['PARint_BL'] * 3600 / 2.02 * 10 ** -6
    RGint_BL_cum = np.cumsum(toto.RGint_BL_MJ)

    df_axe['sum_dry_mass_shoot_couvert'] = df_axe.sum_dry_mass_shoot * plant_density
    df_axe['sum_dry_mass_couvert'] = df_axe.sum_dry_mass * plant_density

    RUE_shoot_couvert = np.polyfit(RGint_BL_cum, df_axe.sum_dry_mass_shoot_couvert, 1)[0]
    RUE_plant_couvert = np.polyfit(RGint_BL_cum, df_axe.sum_dry_mass_couvert, 1)[0]

    # ---  Photosynthetic efficiency of the plant
    df_elt['Photosynthesis_tillers'] = df_elt.Ag * df_elt.green_area * df_elt.nb_replications.fillna(1.)
    df_elt['PARa_tot_tillers'] = df_elt.PARa * df_elt.green_area * df_elt.nb_replications.fillna(1.)
    # df_elt['green_area_tillers'] = df_elt.green_area * df_elt.nb_replications.fillna(1.)
    # photo_y = df_elt.groupby(['t'],as_index=False).agg({'Photosynthesis_tillers':'sum', 'PARa_tot_tillers':'sum', 'green_area_tillers':'sum'})
    # photo_y['Photosynthetic_yield_plante'] = photo_y.Photosynthesis_tillers / photo_y.PARa_tot_tillers

    PARa2 = df_elt.groupby(['t'])['PARa_tot_tillers'].agg('sum')
    PARa2_cum = np.cumsum(PARa2)
    Photosynthesis = df_elt.groupby(['t'])['Photosynthesis_tillers'].agg('sum')
    Photosynthesis_cum = np.cumsum(Photosynthesis)

    avg_photo_y = np.polyfit(PARa2_cum, Photosynthesis_cum, 1)[0]

    # --- Photosynthetic C allocated to Respiration and to Exudation
    C_usages_path = os.path.join(scenario_postprocessing_dirpath, 'C_usages.csv')
    C_usages = pd.read_csv(C_usages_path)
    C_usages_div = C_usages.div(C_usages.C_produced, axis=0)

    # --- Final canopy traits
    t_end = max(df_elt.t)
    df_lamina = df_elt[df_elt.element == 'LeafElement1']
    df_lamina_end = df_lamina[(df_lamina.t == t_end)]
    nb_final_em_leaves = max(df_lamina_end.metamer)
    nb_final_lig_leaves = max(df_lamina_end[~df_lamina_end.is_growing].metamer)

    # average SLA
    df_lamina_end_green = df_lamina_end[(df_lamina_end.green_area > 0) & (df_lamina_end.mstruct > 0)]
    if df_lamina_end_green.shape[0] > 1:
        final_avg_SLA = sum(df_lamina_end_green.green_area) / (sum(df_lamina_end_green.sum_dry_mass) * 10 ** -3)
    else:
        final_avg_SLA = np.nan

    # average phyllochron
    avg_phyllo_df = df_lamina.groupby('metamer', as_index=False).agg({'t': 'min'})
    avg_phyllo_df = avg_phyllo_df.merge(df_axe_out[['t', 'sum_TT']], on='t')
    avg_phyllo_df = avg_phyllo_df[avg_phyllo_df.t > 0]
    Y = avg_phyllo_df['metamer']
    X = avg_phyllo_df['sum_TT']
    X = sm.add_constant(X)
    mod = sm.OLS(Y, X)
    fit_phyllo = mod.fit()

    # ---  Write results into a table
    res_df = pd.DataFrame.from_dict({
        'LAI': [df_LAI.loc[max(df_LAI.index), 'LAI']],
        'RUE_plant_MJ_PAR': [RUE_plant],
        'RUE_shoot_MJ_PAR': [RUE_shoot],
        'RUE_plant_MJ_RGint': [RUE_plant_couvert],
        'RUE_shoot_MJ_RGint': [RUE_shoot_couvert],
        'Photosynthetic_efficiency': [avg_photo_y],
        'C_usages_Respi_roots': C_usages_div.loc[max(C_usages_div.index), 'Respi_roots'],
        'C_usages_Respi_shoot': C_usages_div.loc[max(C_usages_div.index), 'Respi_shoot'],
        'C_usages_Respi': C_usages_div.loc[max(C_usages_div.index), 'Respi_shoot'] + C_usages_div.loc[max(C_usages_div.index), 'Respi_roots'],
        'C_usages_exudation': C_usages_div.loc[max(C_usages_div.index), 'exudation'],
        't_final': [t_end],
        'nb_final_em': [nb_final_em_leaves],
        'nb_final_lig': [nb_final_lig_leaves],
        'final_avg_SLA': [final_avg_SLA],
        'avg_phyllochron': [1 / fit_phyllo.params[1]]
    })

    res_df.to_csv(os.path.join(scenario_postprocessing_dirpath, 'performance_indices.csv'), index=False)

# def all_scenraii_postprocessings(scenarii_list_dirpath):
#     # ------- Run the above functions for all the scenarii
#     # Import scenarii list and description
#     scenarii_df = pd.read_csv(scenarii_list_dirpath, index_col='Scenario')
#     scenarii_df['Scenario'] = scenarii_df.index
#
#     if 'Scenario_label' not in scenarii_df.keys():
#         scenarii_df['Scenario_label'] = ''
#     else:
#         scenarii_df['Scenario_label'] = scenarii_df['Scenario_label'].fillna('')
#     scenarii = scenarii_df.Scenario
#
#
#     for scenario in scenarii:
#         table_C_usages(int(scenario))
#         calculate_performance_indices(int(scenario))
