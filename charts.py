/mount/src/longitudinal/charts.py:34: FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated and will change in a future version. Call result.infer_objects(copy=False) instead. To opt-in to the future behavior, set `pd.set_option('future.no_silent_downcasting', True)`

  return (acute / chronic.replace(0, pd.NA)).fillna(0)

────────────────────── Traceback (most recent call last) ───────────────────────

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/exec_code.py:136 in exec_func_with_error_handling                        

                                                                                

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/script_runner.py:924 in code_to_exec                                     

                                                                                

  /mount/src/longitudinal/app.py:545 in <module>                                

                                                                                

    542 │   │   gps_player_display[dive_cols].apply(pd.to_numeric, errors="coe  

    543 │   )                                                                   

    544 gk_panel("Dives", "Dives (L+C+R)", "chart_dives", charts.GOLD, charts.  

  ❱ 545                                                                         

                                                                                

  /mount/src/longitudinal/app.py:539 in gk_panel                                

                                                                                

    536                                                                         

    537 gk_panel("Jumps", "Total Jumps", "chart_jumps", charts.GREEN, charts.L  

    538 # Dives = left + centre + right dive counts added together              

  ❱ 539 dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count  

    540 if all(c in gps_player_display.columns for c in dive_cols):             

    541 │   gps_player_display["Dives (L+C+R)"] = (                             

    542 │   │   gps_player_display[dive_cols].apply(pd.to_numeric, errors="coe  

────────────────────────────────────────────────────────────────────────────────

TypeError: chart_daily_count() got an unexpected keyword argument 'match_lines'

/mount/src/longitudinal/charts.py:34: FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated and will change in a future version. Call result.infer_objects(copy=False) instead. To opt-in to the future behavior, set `pd.set_option('future.no_silent_downcasting', True)`

  return (acute / chronic.replace(0, pd.NA)).fillna(0)

────────────────────── Traceback (most recent call last) ───────────────────────

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/exec_code.py:136 in exec_func_with_error_handling                        

                                                                                

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/script_runner.py:924 in code_to_exec                                     

                                                                                

  /mount/src/longitudinal/app.py:545 in <module>                                

                                                                                

    542 │   )                                                                   

    543                                                                         

    544                                                                         

  ❱ 545 gk_panel("Jumps", "Total Jumps", "chart_jumps", charts.GREEN, charts.L  

    546 # Dives = left + centre + right dive counts added together              

    547 dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count  

    548 if all(c in gps_player_display.columns for c in dive_cols):             

                                                                                

  /mount/src/longitudinal/app.py:539 in gk_panel                                

                                                                                

    536 │   │   return                                                          

    537 │   render_panel(                                                       

    538 │   │   title,                                                          

  ❱ 539 │   │   charts.chart_daily_count(gps_player_display, col, color, title  

    540 │   │   key=key,                                                        

    541 │   │   legend_items=legend,                                            

    542 │   )                                                                   

────────────────────────────────────────────────────────────────────────────────

TypeError: chart_daily_count() got an unexpected keyword argument 'match_lines'

/mount/src/longitudinal/charts.py:34: FutureWarning: Downcasting object dtype arrays on .fillna, .ffill, .bfill is deprecated and will change in a future version. Call result.infer_objects(copy=False) instead. To opt-in to the future behavior, set `pd.set_option('future.no_silent_downcasting', True)`

  return (acute / chronic.replace(0, pd.NA)).fillna(0)

────────────────────── Traceback (most recent call last) ───────────────────────

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/exec_code.py:136 in exec_func_with_error_handling                        

                                                                                

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/script_runner.py:924 in code_to_exec                                     

                                                                                

  /mount/src/longitudinal/app.py:545 in <module>                                

                                                                                

    542 │   )                                                                   

    543                                                                         

    544                                                                         

  ❱ 545 gk_panel("Jumps", "Total Jumps", "chart_jumps", charts.GREEN, charts.L  

    546 # Dives = left + centre + right dive counts added together              

    547 dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count  

    548 if all(c in gps_player_display.columns for c in dive_cols):             

                                                                                

  /mount/src/longitudinal/app.py:539 in gk_panel                                

                                                                                

    536 │   │   return                                                          

    537 │   render_panel(                                                       

    538 │   │   title,                                                          

  ❱ 539 │   │   charts.chart_daily_count(gps_player_display, col, color, title  

    540 │   │   key=key,                                                        

    541 │   │   legend_items=legend,                                            

    542 │   )                                                                   

────────────────────────────────────────────────────────────────────────────────

TypeError: chart_daily_count() got an unexpected keyword argument 'match_lines'

────────────────────── Traceback (most recent call last) ───────────────────────

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/exec_code.py:136 in exec_func_with_error_handling                        

                                                                                

  /home/adminuser/venv/lib/python3.12/site-packages/streamlit/runtime/scriptru  

  nner/script_runner.py:924 in code_to_exec                                     

                                                                                

  /mount/src/longitudinal/app.py:545 in <module>                                

                                                                                

    542 │   )                                                                   

    543                                                                         

    544                                                                         

  ❱ 545 gk_panel("Jumps", "Total Jumps", "chart_jumps", charts.GREEN, charts.L  

    546 # Dives = left + centre + right dive counts added together              

    547 dive_cols = ["Dive Left Count", "Dive Centre Count", "Dive Right Count  

    548 if all(c in gps_player_display.columns for c in dive_cols):             

                                                                                

  /mount/src/longitudinal/app.py:539 in gk_panel                                

                                                                                

    536 │   │   return                                                          

    537 │   render_panel(                                                       

    538 │   │   title,                                                          

  ❱ 539 │   │   charts.chart_daily_count(gps_player_display, col, color, title  

    540 │   │   key=key,                                                        

    541 │   │   legend_items=legend,                                            

    542 │   )                                                                   

────────────────────────────────────────────────────────────────────────────────

TypeError: chart_daily_count() got an unexpected keyword argument 'match_lines'
